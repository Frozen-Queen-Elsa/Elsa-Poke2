"""
PokeballAI - a Pokemon Detecting DeepCNN Model
"""

# pylint: disable=no-member, wrong-import-position

import asyncio
import warnings
from io import BytesIO
from typing import Optional, Union

import aiohttp
import torch
from PIL import Image
from torch.autograd import Variable
from torchvision import transforms

warnings.filterwarnings("ignore")


class ConditionalPad:
    """Custom Transformer for variable sized input images."""

    # pylint: disable=too-few-public-methods

    def __call__(self, image: Image.Image):
        width, height = image.size
        if (width, height) == (800, 500):
            return image
        if (width, height) <= (800, 500):
            wpad = (800 - width) // 2
            hpad = (500 - height) // 2
            padding = (wpad, hpad, wpad, hpad)
            padder = transforms.Pad(padding, 0, 'constant')
            return padder.__call__(image)
        resizer = transforms.Resize((800, 500))
        return resizer.__call__(image)


class PokeDetector:
    """The API for AI based Detection of Pokemons.

    Queries a custom trained AI model for pokemon's name by giving it an image.

    Attributes
    ----------
    classes_path : str
        path to a text file containing pokemon names the model was trained on.
    model_path : str
        path to the trained AI model.
    session : aiohttp.ClientSession
        an existing asynchronous http session could be passed.
        Will create one if none.

    Methods
    -------
    get_image_path(url)
        Downloads an image from a remote url into a file-like object.

    predict(image_path, mode='local')
        Reads the image and tries to predict its name using the trained model.
    """
    def __init__(
        self, classes_path: str = '../data/pokeclasses.txt',
        model_path: str = '../data/pokemodel.pth',
        session: Optional[aiohttp.ClientSession] = None
    ):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = torch.load(model_path, map_location=self.device)
        self.model.eval()
        txs = [
            ConditionalPad(),
            transforms.Resize((200, 125)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            )
        ]
        self.transforms = transforms.Compose(txs)
        with open(classes_path, encoding='utf-8') as cls_file:
            self.classes = sorted(cls_file.read().splitlines())
        self.session = session

    async def get_image_path(self, url: str) -> BytesIO:
        """
        Downloads an image from a remote url into a file-like object.
        """
        if not self.session:
            self.session = aiohttp.ClientSession(
                loop=asyncio.get_event_loop()
            )
        async with self.session.get(url) as resp:
            data = await resp.read()
        return BytesIO(data)

    def predict(self, image_path: Union[str, BytesIO]) -> str:
        """
        Reads the image and tries to predict is name using the trained model.
        """
        image = Image.open(image_path).convert('RGB')
        image = self.transforms(image).float()
        image = Variable(image, requires_grad=True)
        image = image.unsqueeze(0)
        image = image.to(self.device)
        output = self.model(image)
        index = output.data.cpu().numpy().argmax()
        sftmx = torch.nn.Softmax()
        probabilities = sftmx(output)
        return (str(self.classes[index]), probabilities[0][index].item())
