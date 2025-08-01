class BaseTTS(object):
    
    def __init__(self):
        super(BaseTTS, self).__init__()
        pass

    def text_to_speech(text):
        raise NotImplementedError

    def html_to_speech(html_text: str, output_file: str, metadata):
        raise NotImplementedError
    