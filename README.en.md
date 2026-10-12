# StepFun Cookbook

[简体中文](https://github.com/stepfun-ai/Step-Cookbook/blob/main/README.md) | **English**

Practical guides, runnable examples, and setup tools for building with StepFun models. Start with a specific task, understand how the example works, and adapt it to your own application.

This repository brings together Cookbook content in one place, with more examples to come. Each guide explains a concrete task and includes the steps, sample inputs, code, and expected results needed to reproduce it.

## What you'll find

- **Getting started:** Set up an environment, configure API access, and make your first request.
- **Practical workflows:** Extract structured data from images, connect models to tools, and work with realtime voice and speech synthesis.
- **Implementation techniques:** Organize prompts, handle responses, compare parameters, and reuse code in your application.
- **Setup tools:** Configure development tools to connect to StepFun services.

Examples are provided as Markdown guides, Python scripts, and Jupyter Notebooks. See [Available content](#available-content) for the current collection.

## Repository layout

```text
Step-Cookbook/
├── README.md            # Repository overview in Simplified Chinese
├── README.en.md         # Repository overview in English
├── examples/            # One directory per Cookbook example
├── scripts/             # Standalone utility and setup scripts
│   └── claude-key-setup/ # Configure Claude Code to use StepFun
├── assets/              # Assets shared by multiple examples
└── data/                # Data shared by multiple examples
```

Keep files for a specific example together. Its code, images, recordings, and data belong in its own directory; use the root `assets/` and `data/` directories for resources shared across examples. Empty directories may contain a `.gitkeep` placeholder.

For example, a document-extraction guide could use this layout:

```text
examples/
└── document-extraction/
    ├── README.md        # Task, setup, usage, and expected results
    ├── example.ipynb    # Notebook implementation; a Python script is another option
    ├── requirements.txt # Python dependencies, when needed
    ├── data/            # Input documents for this example
    └── assets/          # Images, screenshots, and diagrams
```

This layout is illustrative; the repository does not yet include a document-extraction example.

## How to use this repository

1. **Choose a guide.** Find a task in the table below and open its English guide. Read the prerequisites before running the code.
2. **Prepare the environment.** Follow the guide's setup instructions, obtain any required assets, and configure an API key with access to the relevant model and region. The five model examples below use `STEP_API_KEY` and prompt for it with the input hidden if the variable is not set.
3. **Run the example.** Follow the Python code blocks in the guide, or use the companion script or Notebook. When using the launchers, obtain the complete example directory and keep its relative paths intact.
4. **Inspect and adapt.** Check the recorded results, then replace the sample inputs and adjust the parameters for your task.

Environment requirements and dependencies vary by example. Initial launcher setup downloads the required runtime and dependencies. Live API calls require network access. Follow the instructions for the example you choose. Keep real API keys out of committed code, Notebooks, and output files.

The English and Chinese guides cover the same model capabilities and main workflows, but prompts, sample inputs, result field names, and validation details may differ. The five examples' companion Python scripts, Notebooks, launcher menus, and directory-level setup guides currently follow the Chinese version. To reproduce the English examples, use the code in the English guide. Each guide ends with links to its companion files and starter project.

## Standalone tools

The `scripts/` directory contains tools that can be used independently of a particular example. Code used by only one example belongs in that example's directory.

- Use a descriptive filename for a single-file tool.
- Give tools with multiple files or platform-specific versions their own directory.
- Document each tool's purpose, prerequisites, commands, inputs, outputs, and any files it changes.

[Claude Key Setup: English guide](https://github.com/stepfun-ai/Step-Cookbook/blob/main/scripts/claude-key-setup/en/README.md) provides dedicated English Bash and PowerShell scripts for configuring Claude Code with a StepFun API key and endpoint. A [Simplified Chinese guide](https://github.com/stepfun-ai/Step-Cookbook/blob/main/scripts/claude-key-setup/zh-CN/README.md) is also available.

## Adding a Cookbook

Make each example easy to understand, run, and adapt. Include the following:

| Topic | What to explain |
| --- | --- |
| Goal | The problem the example solves and when to use it |
| Prerequisites | The environment, dependencies, model access, and input data required |
| Implementation | How to run the code and why the key steps are needed |
| Results | What the output contains and how to check whether it meets the task requirements |
| Scope | Limitations, common issues, and parameters readers can change |

Prefer public, anonymized, or synthetic sample data, and identify its source or nature. Before committing, review Notebook outputs and remove credentials, personal information, and unnecessary logs. Preserve attribution and license information for third-party code, data, and assets.

The [Cookbook writing guide](https://github.com/stepfun-ai/Step-Cookbook/blob/main/.github/COOKBOOK_WRITING_GUIDE.md) is available in Simplified Chinese for authors and editors.

## Available content

| Cookbook | What you'll build or compare | Companion project |
| --- | --- | --- |
| [Step 5 Preview: Reasoning effort](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/step-5-reasoning/en/README.md) | Compare answer quality, response time, and token usage across reasoning effort levels. | [Files and setup](https://github.com/stepfun-ai/Step-Cookbook/tree/main/examples/step-5-reasoning) |
| [Step 5 Preview: Image understanding and structured outputs](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/step-5-vision-structured/en/README.md) | Extract table values from images into JSON and check the structure and values. | [Files and setup](https://github.com/stepfun-ai/Step-Cookbook/tree/main/examples/step-5-vision-structured) |
| [Step 5 Preview: Tool calling](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/step-5-tool-calling/en/README.md) | Implement a loop that validates tool arguments, executes functions, and returns results to the model. | [Files and setup](https://github.com/stepfun-ai/Step-Cookbook/tree/main/examples/step-5-tool-calling) |
| [StepAudio 3 Realtime: Voice conversation and VAD](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/stepaudio-3-realtime/en/README.md) | Build a voice conversation, handle turn events and interruptions, and tune voice activity detection. | [Files and setup](https://github.com/stepfun-ai/Step-Cookbook/tree/main/examples/stepaudio-3-realtime) |
| [StepAudio 3 TTS: Speech synthesis and personalized voices](https://github.com/stepfun-ai/Step-Cookbook/blob/main/examples/stepaudio-3-tts/en/README.md) | Generate WAV audio, compare speaking rates and pronunciation settings, and create a personalized voice from a reference recording. | [Files and setup](https://github.com/stepfun-ai/Step-Cookbook/tree/main/examples/stepaudio-3-tts) |

Standalone tool: [Claude Key Setup](https://github.com/stepfun-ai/Step-Cookbook/blob/main/scripts/claude-key-setup/en/README.md), with English Bash and PowerShell setup scripts.

Add an entry here when contributing a new example so readers can find it from the repository overview.
