# Masterthesis

## Starting the application

### Requirements

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

Then copy the configuration file:

```powershell
Copy-Item .env.example .env
```

The specified PostgreSQL database must already exist. The tables are created automatically when the application starts.