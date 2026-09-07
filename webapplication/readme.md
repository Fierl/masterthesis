# Webapplication

## Requirements

- Python 3.11 or newer
- PostgreSQL
- AWS Bedrock credentials for text generation

### Installation

```powershell
cd webapplication
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy the configuration file.

The specified PostgreSQL database must already exist. The tables are created automatically when the application starts.