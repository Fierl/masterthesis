import os
import boto3
from botocore.config import Config as BotocoreConfig
from src.prompts import SystemPrompts
from src.config.config import Config

def get_bedrock_client():
    try:
        if Config.AWS_BEARER_TOKEN_BEDROCK:
            os.environ['AWS_BEARER_TOKEN_BEDROCK'] = Config.AWS_BEARER_TOKEN_BEDROCK
        
        boto_config = BotocoreConfig(
            region_name=Config.AWS_REGION,
            signature_version='v4',
            retries={'max_attempts': 3, 'mode': 'standard'}
        )
        
        if Config.AWS_ACCESS_KEY_ID and Config.AWS_SECRET_ACCESS_KEY:
            return boto3.client(
                service_name='bedrock-runtime',
                region_name=Config.AWS_REGION,
                aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
                config=boto_config
            )
        else:
            return boto3.client(
                service_name='bedrock-runtime',
                region_name=Config.AWS_REGION,
                config=boto_config
            )
    except Exception as e:
        raise Exception(f"Error: {str(e)}")


def generate_content(prompt, field_name=None, system_instruction=None, context=None, user=None, timeout=30):
    if system_instruction is None and field_name:
        base_prompt = SystemPrompts.get_prompt(field_name)
        
        if user and hasattr(user, 'get_custom_prompt'):
            custom_prompt = user.get_custom_prompt(field_name)
            if custom_prompt is not None and custom_prompt.strip():
                system_instruction = f"{base_prompt}\n\n--- Additional Instructions ---\n{custom_prompt}"
            else:
                system_instruction = base_prompt
        else:
            system_instruction = base_prompt
    elif system_instruction is None:
        system_instruction = SystemPrompts.DEFAULT
    
    if context:
        enhanced_prompt = f"Context:\n{context}\n\nTask:\n{prompt}"
    else:
        enhanced_prompt = prompt
    
    try:
        client = get_bedrock_client()
        
        messages = [
            {
                "role": "user",
                "content": [{"text": enhanced_prompt}]
            }
        ]
        
        system_prompts = [{"text": system_instruction}]
        
        inference_config = {
            "maxTokens": 4096,
            "temperature": 0.5
        }
        
        response = client.converse(
            modelId=Config.BEDROCK_MODEL_ID,
            messages=messages,
            system=system_prompts,
            inferenceConfig=inference_config
        )
        
        output_message = response['output']['message']
        generated_text = output_message['content'][0]['text']
        
        return generated_text
        
    except client.exceptions.ValidationException as e: # type: ignore
        raise Exception(f"Validation error: {str(e)}")
    except client.exceptions.ThrottlingException as e: # type: ignore
        raise Exception("Too many requests. Please wait a moment.") 
    except client.exceptions.ModelTimeoutException as e: # type: ignore
        raise Exception("The API request took too long. Please try again.") 
    except client.exceptions.AccessDeniedException as e: # type: ignore
        raise Exception("Access denied. Please check your AWS credentials and permissions.")
    except client.exceptions.ServiceQuotaExceededException as e: # type: ignore
        raise Exception("Service quota exceeded. Please contact the administrator.")
    except Exception as e:
        error_message = str(e).lower()
        if "timeout" in error_message:
            raise Exception("The API request took too long. Please try again.")
        elif "rate limit" in error_message or "throttl" in error_message:
            raise Exception("Too many requests. Please wait a moment.")
        elif "credentials" in error_message or "access" in error_message:
            raise Exception("AWS authentication failed. Please check your credentials.")
        else:
            raise Exception(f"API error: {str(e)}")