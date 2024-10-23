from feature_extraction_server.core.model import Model
from simple_plugin_manager.settings import FlagSetting
from collections import OrderedDict
import hashlib
import gc
import logging
logger = logging.getLogger(__name__)

class LRUCache:
    def __init__(self, maxsize=100):
        self.cache = OrderedDict()
        self.maxsize = maxsize

    def cache_get(self, key):
        try:
            value = self.cache.pop(key)
            # Re-insert to mark as most recently used
            self.cache[key] = value
            return value
        except KeyError:
            return None

    def cache_set(self, key, value):
        try:
            self.cache.pop(key)
        except KeyError:
            if len(self.cache) >= self.maxsize:
                self.cache.popitem(last=False)
        self.cache[key] = value

def is_cuda_available():
    if not torch.cuda.is_available():
        return False
    try:
        # Try to perform a simple CUDA operation
        torch.zeros(1).to('cuda')
        return True
    except Exception:
        return False

class OpenClipVitB32(Model):

    def _load_model(self):
        global F, torch, np
        import torch.nn.functional as F
        import torch
        import open_clip
        import numpy as np
        
        no_cuda_setting = FlagSetting("NO_CUDA", "If set, the model will not use CUDA.")
        self.no_cuda = no_cuda_setting.get()
        
        if is_cuda_available():
            if self.no_cuda:
                logger.debug("CUDA is available but not being used due to --no-cuda setting.")
                self.device = torch.device("cpu")
            else:
                logger.debug("CUDA is available and being used.")
                self.device = torch.device("cuda")
        else:
            logger.debug("CUDA is not available. Using CPU.")
            self.device = torch.device("cpu")

        model, _, preprocess = open_clip.create_model_and_transforms(
            'xlm-roberta-base-ViT-B-32',
            pretrained='laion5b_s13b_b90k'
        )
        self.model = model.to(self.device)
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer('xlm-roberta-base-ViT-B-32')
        self.transform_image = preprocess

        # Initialize caches
        self.text_cache = LRUCache(maxsize=100)
        self.image_cache = LRUCache(maxsize=100)

    def serialize_image(self, image):
        # Convert image to bytes and hash it for a consistent cache key
        image_array = np.array(image.to_pillow())
        image_bytes = image_array.tobytes()
        image_hash = hashlib.md5(image_bytes).hexdigest()
        return image_hash

    def batched_text_embedding(self, text, config={}):
        results = [None] * len(text)
        uncached_texts = []
        uncached_indices = []

        for idx, t in enumerate(text):
            cached_result = self.text_cache.cache_get(t)
            if cached_result is not None:
                results[idx] = cached_result
            else:
                uncached_texts.append(t)
                uncached_indices.append(idx)

        if uncached_texts:
            tokenized_texts = self.tokenizer(uncached_texts).to(self.device)
            with torch.no_grad():
                text_features = F.normalize(
                    self.model.encode_text(tokenized_texts), p=2, dim=-1
                )
            text_features_list = text_features.cpu().tolist()

            for i, idx in enumerate(uncached_indices):
                embedding = text_features_list[i]
                self.text_cache.cache_set(text[idx], embedding)
                results[idx] = embedding

            gc.collect()

        return {"embedding": results}
    
    def batched_image_embedding(self, image, config={}):
        results = [None] * len(image)
        uncached_images = []
        uncached_indices = []

        for idx, img in enumerate(image):
            image_key = self.serialize_image(img)
            cached_result = self.image_cache.cache_get(image_key)
            if cached_result is not None:
                results[idx] = cached_result
            else:
                uncached_images.append(img)
                uncached_indices.append(idx)

        if uncached_images:
            preprocessed_images = [
                self.transform_image(x.to_pillow())[:3] for x in uncached_images
            ]
            img_array = np.stack(preprocessed_images)
            img_tensor = torch.from_numpy(img_array).to(self.device)
            with torch.no_grad():
                image_features = F.normalize(
                    self.model.encode_image(img_tensor), p=2, dim=-1
                )
            image_features_list = image_features.cpu().tolist()

            for i, idx in enumerate(uncached_indices):
                embedding = image_features_list[i]
                image_key = self.serialize_image(image[idx])
                self.image_cache.cache_set(image_key, embedding)
                results[idx] = embedding

            gc.collect()

        return {"embedding": results}

    def batched_zero_shot_image_classification(self, image, classes, config={}):
        # Get image embeddings
        image_embeddings = self.batched_image_embedding(image, config=config)["embedding"]
        # Get class embeddings
        class_embeddings = self.batched_text_embedding(classes, config=config)["embedding"]

        # Convert embeddings to tensors
        image_features = torch.tensor(image_embeddings, device=self.device)
        text_features = torch.tensor(class_embeddings, device=self.device)

        with torch.no_grad():
            logits_per_image = image_features @ text_features.T
            probabilities = logits_per_image.softmax(dim=-1).cpu().tolist()

        gc.collect()

        return {"probabilities": probabilities}
