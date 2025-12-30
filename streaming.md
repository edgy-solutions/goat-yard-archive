# Streaming Response Architecture

## Overview
We replaced the blocking `dspy.ChainOfThought` execution with a direct `litellm` streaming call to improve user perceived latency. This document captures the architecture, benefits, and trade-offs of this approach.

## Implementation Details

### Previous Architecture (DSPy Blocking)
1.  **Construct**: `bot(question=q, context=ctx)`
2.  **Generate**: DSPy sends full prompt to LLM.
3.  **Wait**: System waits for **entire** generation to complete.
4.  **Assert**: DSPy runs `Assert` checks (e.g., citation verification).
5.  **Retry**: If assertion fails, DSPy automatically rewrites prompt and retries (Self-Correction).
6.  **Return**: Final `SearchResponse` sent to user.

### Current Architecture (LiteLLM Streaming)
1.  **Construct**: Manually formatted Prompt string (Strings together System + Context + Question).
2.  **Stream**: Call `litellm.completion(..., stream=True)`.
3.  **Yield**: `StreamingResponse` yields NDJSON chunks immediately to frontend.
4.  **Verify**: As tokens arrive, we accumulate `answer`. Once finished, we run regex verification.
5.  **Result**: We send a final `{"type": "result", "verified": ...}` block.

## Trade-offs

### ✅ Pros (Benefits)
*   **Time-to-First-Token (TTFT)**: Users see the answer start appearing in ~500ms instead of 5-10s. This is critical for search UX.
*   **Engagement**: "Typing" animation keeps users engaged.
*   **Reliability**: `litellm` handles low-level streaming protocols better than current `dspy` wrappers.

### ❌ Cons (Lost DSPy Features)
*   **Lost Automatic Optimization (Compile)**: We cannot use `dspy.Teleprompter` to automatically optimize the system prompt or few-shot examples based on a metric. We are stuck with our manual string prompt.
*   **Lost Self-Correction**: If the LLM hallucinates a citation, we **cannot prevent the user from seeing it**. We have already streamed it. We can only flag it as "Unverified" *after the fact*. In the previous model, we could catch it, retry, and potentially output a correct answer without the user ever knowing.
*   **Lost Abstraction**: We manually handle prompt formatting, making model swirling (switching to Models with different chat templates) slightly more manual.

## Future Hybrid Strategy
To regain the best of both worlds, we can eventually adopt a **Hybrid Approach**:

1.  **Use DSPy to Optimize**: Use DSPy offline (build time) to "compile" the optimal prompt instructions and few-shot examples.
2.  **Freeze Program**: Save the optimized program state.
3.  **Runtime**: Load the optimized prompt instructions, but feed them into `litellm` for the actual streaming execution.

This allows us to optimize the *inputs* using DSPy, while executing the *output* using the high-performance streaming engine.
