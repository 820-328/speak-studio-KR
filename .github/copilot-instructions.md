# Copilot Instructions for speak-studio-KR

## Overview
This project is a Python-based application designed to interact with OpenAI's Chat Completions API. The codebase is structured to ensure modularity and ease of use, with key components handling API interactions, utility functions, and data management.

## Key Components

### 1. `api_client.py`
- **Purpose**: Provides a wrapper for OpenAI's Chat Completions API.
- **Key Functions**:
  - `chat(messages: List[Dict[str, Any]], model: Optional[str] = None) -> Optional[str]`: Sends a list of messages to the OpenAI API and retrieves the response.
  - `_make_client()`: Initializes the OpenAI client using the API key.
- **Patterns**:
  - Uses `try-import` to handle optional dependencies gracefully.
  - Returns `None` for fallback scenarios when API keys are missing or errors occur.

### 2. `utils.py`
- **Purpose**: Contains utility functions for retrieving API keys and model names.
- **Integration**: Used extensively in `api_client.py` to fetch configuration details.

### 3. `constants.py`
- **Purpose**: Stores constant values used across the project.

### 4. `data/counter.db`
- **Purpose**: Likely a SQLite database for tracking counters or other persistent data.

### 5. `audio/`
- **Structure**:
  - `input/`: Directory for storing input audio files.
  - `output/`: Directory for storing processed audio files.

### 6. `images/`
- **Purpose**: Contains static image assets like `ai_icon.jpg` and `user_icon.jpg`.

## Developer Workflows

### Setting Up the Environment
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Ensure `runtime.txt` specifies the correct Python version.

### Running the Application
- Execute `main.py` to start the application.

### Debugging
- Use `print` statements or logging for debugging API interactions in `api_client.py`.

## Project-Specific Conventions
- **Error Handling**: Functions return `None` on failure to allow UI-level fallback mechanisms.
- **Dynamic Imports**: Optional dependencies are handled using `try-import` to ensure the application doesn't crash if a library is missing.
- **Type Annotations**: The codebase uses Python type hints for better readability and maintainability.

## External Dependencies
- **OpenAI SDK**: Used for interacting with the Chat Completions API.
- **SQLite**: Likely used for data persistence in `data/counter.db`.

## Examples
- **Calling the Chat API**:
  ```python
  from api_client import chat

  messages = [
      {"role": "user", "content": "Hello!"},
      {"role": "assistant", "content": "Hi there!"}
  ]
  response = chat(messages)
  print(response)
  ```

## Notes
- Ensure the OpenAI API key is set up correctly using `utils.get_openai_api_key()`.
- Follow the directory structure for organizing input/output files and static assets.

---

Feel free to update this document as the project evolves.