from dataclasses import dataclass

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
