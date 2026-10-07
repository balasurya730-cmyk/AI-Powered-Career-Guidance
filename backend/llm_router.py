import os

def get_routing_chain(feature: str) -> list[dict]:
    """
    Returns a chain (list) of API configurations to try in order.
    If the first one fails, the system will transparently fallback to the next.
    """
    gemini_default = {
        "provider": "gemini",
        "url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "api_key": os.getenv("GEMINI_API_KEY"),
        "model": os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    }
    
    chain = []
    
    # Read what provider the user wants for this feature from .env
    provider_env_key = f"PROVIDER_{feature.upper()}"
    selected_provider = os.getenv(provider_env_key)
    
    if feature == "ai_chat":
        # Rule: ai_chat gives FIRST priority to Gemini Mentor key, then fallback to Z.AI
        mentor_gemini = gemini_default.copy()
        if os.getenv("GEMINI_API_KEY_MENTOR"):
            mentor_gemini["api_key"] = os.getenv("GEMINI_API_KEY_MENTOR")
        chain.append(mentor_gemini)
        
        # Fallback to Z.AI
        z_ai_key = os.getenv("Z_AI_API_KEY")
        if z_ai_key and not z_ai_key.startswith("your_"):
            chain.append({
                "provider": "openrouter",
                "url": "https://openrouter.ai/api/v1/chat/completions",
                "api_key": z_ai_key,
                "model": os.getenv("Z_AI_MODEL", "nvidia/nemotron-3.5-lightning:free")
            })
            
    else:
        # Default routing logic: Primary Provider from .env -> Fallback to Gemini
        if selected_provider == "LIQUID":
            key = os.getenv("LIQUID_API_KEY")
            if key and not key.startswith("your_"):
                chain.append({
                    "provider": "openrouter",
                    "url": "https://openrouter.ai/api/v1/chat/completions",
                    "api_key": key,
                    "model": os.getenv("LIQUID_MODEL", "nvidia/nemotron-3.5-lightning:free")
                })
        elif selected_provider == "COHERE":
            key = os.getenv("COHERE_API_KEY")
            if key and not key.startswith("your_"):
                chain.append({
                    "provider": "openrouter",
                    "url": "https://openrouter.ai/api/v1/chat/completions",
                    "api_key": key,
                    "model": os.getenv("COHERE_MODEL", "liquid/lfm-40b:free")
                })
        elif selected_provider == "NVIDIA":
            key = os.getenv("OPENROUTER_API_KEY")
            if key and not key.startswith("your_"):
                chain.append({
                    "provider": "openrouter",
                    "url": "https://openrouter.ai/api/v1/chat/completions",
                    "api_key": key,
                    "model": os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3.5-lightning:free")
                })

        # Add the Gemini fallback at the end of the chain
        fallback_gemini = gemini_default.copy()
        if feature in ["career_guidance", "skillgap"] and os.getenv("GEMINI_API_KEY_CAREER"):
            fallback_gemini["api_key"] = os.getenv("GEMINI_API_KEY_CAREER")
        elif feature == "mock_interview" and os.getenv("GEMINI_API_KEY_INTERVIEW"):
            fallback_gemini["api_key"] = os.getenv("GEMINI_API_KEY_INTERVIEW")
            
        chain.append(fallback_gemini)
        
    return chain
