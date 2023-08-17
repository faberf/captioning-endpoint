import torch
from transformers import Blip2Processor, Blip2ForConditionalGeneration, Blip2VisionModel, Blip2Model
from feature_extraction_server.utils import batch

defaults = {}

device = "cuda" if torch.cuda.is_available() else "cpu"

processor = Blip2Processor.from_pretrained("Salesforce/blip2-opt-2.7b")
condgenmodel = Blip2ForConditionalGeneration.from_pretrained(
    "Salesforce/blip2-opt-2.7b", torch_dtype=torch.float
)
condgenmodel.to(device)



def conditional_image_captioning(image, text, config={}):
    # Set defaults if not provided
    args = defaults.copy()
    args.update(config)
    
    inputs = processor(images=list(map(lambda x: x.to_numpy(), image)), text=text, return_tensors="pt")
    inputs = {k: v.to(condgenmodel.device) for k, v in inputs.items()}
    with torch.no_grad():
        output_ids = condgenmodel.generate(**inputs,  **args)
    preds = processor.batch_decode(output_ids, skip_special_tokens=True)
    preds = [pred.strip() for pred in preds]
    return list(batch(preds, len(preds)//len(image)))
