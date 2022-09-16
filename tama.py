import argparse
from pathlib import Path
from typing import List, Union

import numpy as np
from scipy.io import wavfile

from entrainment import calculate_sample_correlation, calculate_time_series
from frame import Frame, MissingFrame
from interpausal_unit import InterPausalUnit

arg_parser = argparse.ArgumentParser(
    description="Generate a times series for a speaker for a task"
)
arg_parser.add_argument(
    "-a", "--audio-file-a", type=str, help="Audio .wav file for a speaker A"
)
arg_parser.add_argument(
    "-b", "--audio-file-b", type=str, help="Audio .wav file for a speaker B"
)
arg_parser.add_argument(
    "-wa", "--words-file-a", type=str, help=".words file for a speaker A"
)
arg_parser.add_argument(
    "-wb", "--words-file-b", type=str, help=".words file for a speaker B"
)
arg_parser.add_argument(
    "-f", "--feature", type=str, help="Feature to calculate time series"
)
arg_parser.add_argument(
    "-ga", "--pitch-gender-a", type=str, help="Gender of the pitch of speaker A"
)
arg_parser.add_argument(
    "-gb", "--pitch-gender-b", type=str, help="Gender of the pitch of speaker B"
)
arg_parser.add_argument(
    "-l",
    "--lags",
    type=str,
    help="Variation of lags to calculate Sample cross-correlation",
)
arg_parser.add_argument(
    "-e", "--extractor", type=str, help="Extractor to use for calculating IPUs features"
)


def get_interpausal_units(words_fname: Path) -> List[InterPausalUnit]:
    """
    Return a list of IPUs given a Path to a .word file
    """
    interpausal_units: List[InterPausalUnit] = []
    with open(words_fname, encoding="utf-8", mode="r") as word_file:
        IPU_started: bool = False
        IPU_start: float = 0.0
        last_end: float = 0.0
        while line := word_file.readline().rstrip():  # Efficient reading
            start, end, word = line.split()
            word_start, word_end = float(start), float(end)
            if not IPU_started and word == "#":
                IPU_start = 0.0
                last_end = 0.0
            elif not IPU_started and word != "#":
                IPU_start = word_start
                last_end = word_end
                IPU_started = True
            elif IPU_started and word != "#":
                last_end = word_end
            elif IPU_started and word == "#":
                interpausal_units.append(InterPausalUnit(IPU_start, last_end))
                IPU_started = False
        if IPU_start and last_end:  # Last IPU if existent
            interpausal_units.append(InterPausalUnit(IPU_start, last_end))

    return interpausal_units


def has_interval_intersection_with_interpausal_unit(
    interpausal_unit: InterPausalUnit, interval_start: float, interval_end: float
) -> bool:
    res: bool = False

    max_start: float = max(interpausal_unit.start, interval_start)
    min_end: float = min(interpausal_unit.end, interval_end)

    if max_start < min_end:
        res = True
    return res


def interpausal_units_inside_interval(
    interpausal_units: List[InterPausalUnit], interval_start: float, interval_end: float
) -> List[InterPausalUnit]:
    """
    Return a list of the IPUs that have intersection with the interval given
    """
    # POSSIBLE TO-DO: make a logorithmic search
    IPUs: List[InterPausalUnit] = []
    for interpausal_unit in interpausal_units:
        if has_interval_intersection_with_interpausal_unit(
            interpausal_unit, interval_start, interval_end
        ):
            IPUs.append(interpausal_unit)
    return IPUs


def separate_frames(
    interpausal_units: List[InterPausalUnit], data: np.ndarray, samplerate: int
) -> List[Union[Frame, MissingFrame]]:
    """
    Given an audio data and samplerate, return a list of the frames inside
    """

    FRAME_LENGHT: int = 16 * samplerate
    TIME_STEP: int = 8 * samplerate

    frames: List[Union[Frame, MissingFrame]] = []
    audio_length: int = data.shape[0]

    frame_start, frame_end = 0, FRAME_LENGHT
    while frame_start < audio_length:
        # Truncate frame_end
        if frame_end > audio_length:
            frame_end = audio_length

        # Convert frame ends to seconds
        frame_start_in_s: float = frame_start / samplerate
        frame_end_in_s: float = frame_end / samplerate

        IPUs_inside_frame: List[InterPausalUnit] = interpausal_units_inside_interval(
            interpausal_units, frame_start_in_s, frame_end_in_s
        )

        frame = None
        if IPUs_inside_frame:
            frame = Frame(
                start=frame_start_in_s,
                end=frame_end_in_s,
                is_missing=False,
                interpausal_units=IPUs_inside_frame,
            )
        else:
            # A particular frame could contain no IPUs, in which case its a/p feature values are considered ‘missing’
            frame = MissingFrame(
                start=frame_start_in_s,
                end=frame_end_in_s,
            )

        frames.append(frame)

        frame_start += TIME_STEP
        frame_end += TIME_STEP

    return frames


def print_audio_description(speaker: str, wav_fname: Path) -> None:
    samplerate, data = wavfile.read(wav_fname)
    print("----------------------------------------")
    print(f"Audio from speaker {speaker}")
    print(f"Samplerate: {samplerate}")
    print(f"Audio data shape: {data.shape}")
    print(f"Audio data dtype: {data.dtype}")
    print(f"min, max: {data.min()}, {data.max()}")
    print(f"Lenght: {data.shape[0]/samplerate} s")
    print("----------------------------------------")


def get_frames(
    wav_fname: Path,
    words_fname: Path,
) -> List[Union[Frame, MissingFrame]]:
    samplerate, data = wavfile.read(wav_fname)

    interpausal_units: List[InterPausalUnit] = get_interpausal_units(words_fname)

    frames: List[Union[Frame, MissingFrame]] = separate_frames(
        interpausal_units, data, samplerate
    )

    return frames


def main() -> None:
    args = arg_parser.parse_args()

    wav_a_fname: Path = Path(args.audio_file_a)
    words_a_fname: Path = Path(args.words_file_a)
    frames_a: List[Union[Frame, MissingFrame]] = get_frames(wav_a_fname, words_a_fname)
    print(f"Amount of frames of speaker A: {len(frames_a)}")

    print_audio_description("A", wav_a_fname)

    wav_b_fname: Path = Path(args.audio_file_b)
    words_b_fname: Path = Path(args.words_file_b)
    frames_b: List[Union[Frame, MissingFrame]] = get_frames(wav_b_fname, words_b_fname)
    print_audio_description("B", wav_b_fname)
    print(f"Amount of frames of speaker B: {len(frames_b)}")

    if len(frames_a) != len(frames_b):
        raise ValueError("The amount of frames of each speaker is different")

    time_series_a: List[float] = calculate_time_series(
        args.feature, frames_a, wav_a_fname, args.extractor, args.pitch_gender_a
    )
    print("----------------------------------------")
    print(f"Time series of A: {time_series_a}")

    time_series_b: List[float] = calculate_time_series(
        args.feature, frames_b, wav_b_fname, args.extractor, args.pitch_gender_b
    )
    print(f"Time series of B: {time_series_b}")
    print("----------------------------------------")

    print("Sample cross-correlation")
    sample_cross_correlations: List[float] = calculate_sample_correlation(
        time_series_a, time_series_b, int(args.lags)
    )
    print(f"Correlations with lag from 0 to {args.lags}: {sample_cross_correlations}")


if __name__ == "__main__":
    main()
