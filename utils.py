
import base64
import io
from PIL import Image
import soundfile as sf

def prepare_images(images):
    return_list = True
    image_strs = images
    if type(images) is str:
        image_strs = [image_strs]
        return_list = False
    images = []
    for img_string in image_strs:
        if img_string.startswith('data:image'):
            img_string = img_string.split(',', 1)[1]
        img_data = base64.b64decode(img_string)
        image = Image.open(io.BytesIO(img_data))
        if image.mode != "RGB":
            image = image.convert(mode="RGB")
        images.append(image)
    return images, return_list

def prepare_text(text):
    return_list = True
    text = text
    if type(text) is str:
        text = [text]
        return_list = False
    return text, return_list

def batch(iterable, n=1):
    l = len(iterable)
    for ndx in range(0, l, n):
        yield iterable[ndx:min(ndx + n, l)]

def prepare_audio(audio_data_url):
    return_list = True
    audio_data = audio_data_url
    if type(audio_data_url) is str:
        audio_data = [audio_data_url]
        return_list = False
    audio = []
    for audio_string in audio_data:
        if audio_string.startswith('data:audio'):
            audio_string = audio_string.split(',', 1)[1]
        # decode the base64 data
        binary_data = base64.b64decode(audio_string)

        # create a binary stream from the data
        data_stream = io.BytesIO(binary_data)

        # read the audio file from the stream
        samples, sample_rate = sf.read(data_stream)
        audio.append((samples, sample_rate))
    return audio, return_list