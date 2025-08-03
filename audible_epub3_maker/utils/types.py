from dataclasses import dataclass
from pathlib import Path

@dataclass
class WordBoundary:
    """
    Represents a word boundary in synthesized or aligned audio.

    This class is used to represent the start and end of a word in the audio stream.
    
    Attributes:
        start_ms (float): Start time of the word in milliseconds.
        end_ms (float): End time of the word in milliseconds.
        word (str): The actual word that is being represented. For chinese language, this text field may consists of multiple words.
    """
    start_ms: float
    end_ms: float
    text: str

@dataclass
class TagAlignment:
    """
    Represents a force alignment (SMIL) between HTML tags and it's audio strem.

    Attributes:
        tag_id (str): ID of a HTML tag element.
        start_ms (float): Start time of the tag in milliseconds.
        end_ms (float): End time of the tag in milliseconds.
    """
    tag_id: str
    start_ms: float
    end_ms: float


@dataclass
class TaskPayload(object):
    task_id: int | str
    html_text: str
    audio_output_file: Path
    audio_metadata: dict

    def __str__(self):
        return (
            f"<{self.__class__.__name__} "
            f"task_id={self.task_id}, "
            f"audio_output_file={self.audio_output_file}, "
            f"...>"
        )


@dataclass
class TaskResult(object):
    task_id: int | str
    taged_html: str
    audio_file: Path
    alignments: list[TagAlignment]

    def __str__(self):
        return (
            f"<{self.__class__.__name__} "
            f"task_id={self.task_id}, "
            f"{self.audio_file}, {len(self.alignments)} alignments ...>"
        )

@dataclass
class TaskErrorResult(object):
    payload: TaskPayload
    error_type: str
    error_msg: str

    def __str__(self):
        return (
            f"<{self.__class__.__name__} "
            f"task_id={self.payload.task_id}, "
            f"{self.error_type}, {self.error_msg} ...>"
        )

class TTSEmptyContentError(ValueError): pass
class TTSEmptyAudioError(ValueError): pass
class NoWordBoundariesError(RuntimeError): pass