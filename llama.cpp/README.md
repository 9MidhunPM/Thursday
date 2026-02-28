# llama.cpp Runtime

This directory contains only the runtime files needed to run the llama-server.
The full llama.cpp source is **not** included in this repo.

## Setup

1. **Download the model** — place your `.gguf` model in `models/`:
   ```
   models/meta-llama-3-8b-instruct.Q4_K_M.gguf
   ```

2. **Build llama-server** — clone and build the full [llama.cpp](https://github.com/ggerganov/llama.cpp) repo,
   then copy these files into `build/bin/Release/`:
   - `llama-server.exe`
   - `ggml-base.dll`
   - `ggml-cpu.dll`
   - `ggml-vulkan.dll`
   - `ggml.dll`
   - `llama.dll`
   - `mtmd.dll`

3. **Start the server** — run `start-server.bat` from the repo root.
