"""
DSPy Prompt Optimization Script

Uses the 70 verified input/output pairs to optimize the normalization prompt
using DSPy's BootstrapFewShot optimizer.
"""

import os
import re
import json
import dspy
from pathlib import Path
from typing import List, Tuple
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Import the verification function from normalize_markdown
from normalize_markdown import verify_normalization, SYSTEM_PROMPT


def load_training_examples(normalized_dir: str) -> List[Tuple[str, str]]:
    """Load all verified input/output pairs from the normalized directory."""
    examples = []
    norm_dir = Path(normalized_dir)
    
    for norm_file in sorted(norm_dir.glob("*_normalized.md")):
        # Get corresponding source file
        source_name = norm_file.name.replace("_normalized.md", ".md")
        source_file = norm_dir / source_name
        
        if not source_file.exists():
            logging.warning(f"Source file not found for {norm_file.name}")
            continue
        
        with open(source_file, 'r', encoding='utf-8') as f:
            source = f.read()
        with open(norm_file, 'r', encoding='utf-8') as f:
            normalized = f.read()
        
        # Verify the pair passes our checks
        result = verify_normalization(source, normalized)
        if result.passed:
            examples.append((source, normalized))
            logging.info(f"Loaded: {norm_file.name}")
        else:
            logging.warning(f"Skipped (failed verification): {norm_file.name}")
    
    return examples


class NormalizeGillMarkdown(dspy.Signature):
    """Normalize OCR-extracted markdown from John Gill's Bible Commentary."""
    raw_markdown: str = dspy.InputField(desc="Raw OCR markdown to normalize")
    normalized_markdown: str = dspy.OutputField(desc="Clean, normalized markdown")


class GillNormalizer(dspy.Module):
    """DSPy module for normalizing Gill's Commentary markdown."""
    
    def __init__(self):
        super().__init__()
        self.predictor = dspy.ChainOfThought(NormalizeGillMarkdown)
        self.system_prompt = SYSTEM_PROMPT
    
    def forward(self, raw_markdown: str) -> dspy.Prediction:
        # Prepend system prompt context to the input
        prompt = f"{self.system_prompt}\n\n---\n\nPlease normalize the following raw OCR markdown:\n\n{raw_markdown}"
        result = self.predictor(raw_markdown=prompt)
        return dspy.Prediction(normalized_markdown=result.normalized_markdown)


def verification_metric(example, prediction, trace=None) -> float:
    """
    Metric function for DSPy optimization.
    Returns 1.0 if verification passes, 0.0 otherwise.
    """
    try:
        # Handle both dspy.Prediction objects and raw strings
        if hasattr(prediction, 'normalized_markdown'):
            pred_text = prediction.normalized_markdown
        elif isinstance(prediction, str):
            pred_text = prediction
        else:
            pred_text = str(prediction)
        
        result = verify_normalization(example.raw_markdown, pred_text)
        return 1.0 if result.passed else 0.0
    except Exception as e:
        logging.error(f"Verification error: {e}")
        return 0.0


def train_optimizer(
    examples: List[Tuple[str, str]],
    model: str = "deepseek/deepseek-chat",
    output_path: str = "optimized_normalizer.json",
    num_fewshot: int = 3,
    max_examples: int = 50
):
    """
    Train the DSPy prompt using BootstrapFewShot optimizer.
    
    Args:
        examples: List of (source, normalized) pairs
        model: The LLM model to use
        output_path: Where to save the optimized prompt
        num_fewshot: Number of few-shot examples to include
        max_examples: Maximum training examples to use
    """
    # Configure DSPy LM
    api_key = os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable not set")
    
    lm = dspy.LM(
        model=f"openrouter/{model}",
        api_key=api_key,
        temperature=0.0
    )
    dspy.configure(lm=lm)
    
    # Create training examples
    train_examples = []
    for source, normalized in examples[:max_examples]:
        train_examples.append(dspy.Example(
            raw_markdown=source,
            normalized_markdown=normalized
        ).with_inputs("raw_markdown"))
    
    logging.info(f"Loaded {len(train_examples)} training examples")
    
    # Split into train/dev sets
    split_idx = int(len(train_examples) * 0.8)
    trainset = train_examples[:split_idx]
    devset = train_examples[split_idx:]
    
    logging.info(f"Train set: {len(trainset)}, Dev set: {len(devset)}")
    
    # Create the module to optimize
    normalizer = GillNormalizer()
    
    # Create optimizer
    from dspy.teleprompt import BootstrapFewShot
    
    optimizer = BootstrapFewShot(
        metric=verification_metric,
        max_bootstrapped_demos=num_fewshot,
        max_labeled_demos=num_fewshot
    )
    
    # Optimize
    logging.info("Starting optimization...")
    optimized_normalizer = optimizer.compile(
        normalizer,
        trainset=trainset
    )
    
    # Evaluate on dev set
    logging.info("Evaluating on dev set...")
    correct = 0
    for example in devset:
        try:
            pred = optimized_normalizer(raw_markdown=example.raw_markdown)
            # Handle both Prediction objects and strings
            pred_text = pred.normalized_markdown if hasattr(pred, 'normalized_markdown') else str(pred)
            result = verify_normalization(example.raw_markdown, pred_text)
            if result.passed:
                correct += 1
        except Exception as e:
            logging.error(f"Evaluation error: {e}")
    
    accuracy = correct / len(devset) if devset else 0
    logging.info(f"Dev set accuracy: {accuracy:.2%} ({correct}/{len(devset)})")
    
    # Save optimized module
    optimized_normalizer.save(output_path)
    logging.info(f"Saved optimized normalizer to {output_path}")
    
    return optimized_normalizer, accuracy


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Train DSPy prompt optimizer for Gill's Commentary normalization")
    parser.add_argument("--dir", "-d", 
                        default=r"C:\Users\cnogr\git\extract\extracted_images\qwen_qwen3-vl-235b-a22b-thinking",
                        help="Directory containing source and normalized files")
    parser.add_argument("--model", "-m",
                        default="deepseek/deepseek-chat",
                        help="LLM model to use for optimization")
    parser.add_argument("--output", "-o",
                        default="optimized_normalizer.json",
                        help="Output path for optimized model")
    parser.add_argument("--num-fewshot", "-n",
                        type=int, default=3,
                        help="Number of few-shot examples to include")
    parser.add_argument("--max-examples", "-x",
                        type=int, default=50,
                        help="Maximum training examples to use")
    
    args = parser.parse_args()
    
    # Load examples
    examples = load_training_examples(args.dir)
    logging.info(f"Loaded {len(examples)} verified examples")
    
    if len(examples) < 5:
        logging.error("Not enough examples for training. Need at least 5.")
        return
    
    # Train
    optimized, accuracy = train_optimizer(
        examples=examples,
        model=args.model,
        output_path=args.output,
        num_fewshot=args.num_fewshot,
        max_examples=args.max_examples
    )
    
    logging.info(f"Optimization complete! Dev accuracy: {accuracy:.2%}")


if __name__ == "__main__":
    main()
