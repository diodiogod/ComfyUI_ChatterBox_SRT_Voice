# Version and constants
VERSION = "2.0.2"
IS_DEV = False  # Set to False for release builds
VERSION_DISPLAY = f"v{VERSION}" + (" (dev)" if IS_DEV else "")
SEPARATOR = "=" * 70

"""
ComfyUI Custom Nodes for ChatterboxTTS - Voice Edition
Enhanced with bundled ChatterBox support and improved chunking
SUPPORTS: Bundled ChatterBox (recommended) + System ChatterBox (fallback)
"""

import warnings
warnings.filterwarnings('ignore', message='.*PerthNet.*')
warnings.filterwarnings('ignore', message='.*LoRACompatibleLinear.*')
warnings.filterwarnings('ignore', message='.*requires authentication.*')

import os
import folder_paths

# Import new node implementations
# Use absolute imports to avoid relative import issues when loaded via importlib
import sys
import os
import importlib.util

# Add current directory to path for absolute imports
current_dir = os.path.dirname(__file__)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import nodes using direct file loading to avoid package path issues
def load_node_module(module_name, file_name):
    """Load a node module from the nodes directory"""
    module_path = os.path.join(current_dir, "nodes", file_name)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    # Add to sys.modules to allow internal imports within the module
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# Load node modules
tts_module = load_node_module("chatterbox_tts_node", "tts_node.py")
vc_module = load_node_module("chatterbox_vc_node", "vc_node.py")
audio_recorder_module = load_node_module("chatterbox_audio_recorder_node", "audio_recorder_node.py")

ChatterboxTTSNode = tts_module.ChatterboxTTSNode
ChatterboxVCNode = vc_module.ChatterboxVCNode
ChatterBoxVoiceCapture = audio_recorder_module.ChatterBoxVoiceCapture

# Import foundation components for compatibility
from core.import_manager import import_manager

# Legacy compatibility - keep these for existing workflows
GLOBAL_AUDIO_CACHE = {}
NODE_DIR = os.path.dirname(__file__)
BUNDLED_CHATTERBOX_DIR = os.path.join(NODE_DIR, "chatterbox")
BUNDLED_MODELS_DIR = os.path.join(NODE_DIR, "models", "chatterbox")

# Get availability status from import manager
availability = import_manager.get_availability_summary()
CHATTERBOX_TTS_AVAILABLE = availability["tts"]
CHATTERBOX_VC_AVAILABLE = availability["vc"]
CHATTERBOX_AVAILABLE = availability["any_chatterbox"]
USING_BUNDLED_CHATTERBOX = True  # Default assumption

def find_chatterbox_models():
    """Find ChatterBox model files in order of priority - Legacy compatibility function"""
    model_paths = []
    
    # 1. Check for bundled models in node folder
    bundled_model_path = os.path.join(BUNDLED_MODELS_DIR, "s3gen.pt")
    if os.path.exists(bundled_model_path):
        model_paths.append(("bundled", BUNDLED_MODELS_DIR))
        return model_paths  # Return immediately if bundled models found
    
    # 2. Check ComfyUI models folder - first check the standard location
    comfyui_model_path_standard = os.path.join(folder_paths.models_dir, "chatterbox", "s3gen.pt")
    if os.path.exists(comfyui_model_path_standard):
        model_paths.append(("comfyui", os.path.dirname(comfyui_model_path_standard)))
        return model_paths
    
    # 3. Check legacy location (TTS/chatterbox) for backward compatibility
    comfyui_model_path_legacy = os.path.join(folder_paths.models_dir, "TTS", "chatterbox", "s3gen.pt")
    if os.path.exists(comfyui_model_path_legacy):
        model_paths.append(("comfyui", os.path.dirname(comfyui_model_path_legacy)))
        return model_paths
    
    # 3. HuggingFace download as fallback (only if no local models found)
    model_paths.append(("huggingface", None))
    
    return model_paths

# Import SRT node conditionally
try:
    srt_module = load_node_module("chatterbox_srt_node", "srt_tts_node.py")
    ChatterboxSRTTTSNode = srt_module.ChatterboxSRTTTSNode
    SRT_SUPPORT_AVAILABLE = True
except (ImportError, FileNotFoundError, AttributeError):
    SRT_SUPPORT_AVAILABLE = False
    
    # Create dummy SRT node for compatibility
    class ChatterboxSRTTTSNode:
        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"error": ("STRING", {"default": "SRT support not available"})}}
        
        RETURN_TYPES = ("STRING",)
        FUNCTION = "error"
        CATEGORY = "ChatterBox Voice"
        
        def error(self, error):
            raise ImportError("SRT support not available - missing required modules")

# Update SRT node availability based on import manager
try:
    success, modules, source = import_manager.import_srt_modules()
    if success:
        SRT_SUPPORT_AVAILABLE = True
        # Make SRT modules available for legacy compatibility if needed
        SRTParser = modules.get("SRTParser")
        SRTSubtitle = modules.get("SRTSubtitle")
        SRTParseError = modules.get("SRTParseError")
        AudioTimingUtils = modules.get("AudioTimingUtils")
        TimedAudioAssembler = modules.get("TimedAudioAssembler")
        calculate_timing_adjustments = modules.get("calculate_timing_adjustments")
        AudioTimingError = modules.get("AudioTimingError")
        PhaseVocoderTimeStretcher = modules.get("PhaseVocoderTimeStretcher")
        FFmpegTimeStretcher = modules.get("FFmpegTimeStretcher")
        
        if IS_DEV:
            print(f"✅ SRT TTS node available! (source: {source})")
    else:
        SRT_SUPPORT_AVAILABLE = False
        if IS_DEV:
            print("❌ SRT support not available")
except Exception:
    SRT_SUPPORT_AVAILABLE = False
    if IS_DEV:
        print("❌ SRT support initialization failed")

# Legacy compatibility: Remove old large SRT implementation - it's now in the new node

# Register nodes
NODE_CLASS_MAPPINGS = {
    "ChatterBoxVoiceTTSDiogod": ChatterboxTTSNode,
    "ChatterBoxVoiceVCDiogod": ChatterboxVCNode,
    "ChatterBoxVoiceCaptureDiogod": ChatterBoxVoiceCapture,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ChatterBoxVoiceTTSDiogod": "🎤 ChatterBox Voice TTS (diogod)",
    "ChatterBoxVoiceVCDiogod": "🔄 ChatterBox Voice Conversion (diogod)",
    "ChatterBoxVoiceCaptureDiogod": "🎙️ ChatterBox Voice Capture (diogod)",
}

# Add SRT node if available
if SRT_SUPPORT_AVAILABLE:
    NODE_CLASS_MAPPINGS["ChatterBoxSRTVoiceTTS"] = ChatterboxSRTTTSNode
    NODE_DISPLAY_NAME_MAPPINGS["ChatterBoxSRTVoiceTTS"] = "📺 ChatterBox SRT Voice TTS"

# Print startup banner
print(SEPARATOR)
print(f"🚀 ChatterBox Voice Extension {VERSION_DISPLAY}")

# Check for local models
model_paths = find_chatterbox_models()
first_source = model_paths[0][0] if model_paths else None
print(f"Using model source: {first_source}")

if first_source == "bundled":
    print("✓ Using bundled models")
elif first_source == "comfyui":
    print("✓ Using ComfyUI models")
elif first_source == "huggingface":
    print("⚠️ No local models found - will download from Hugging Face")
    print("💡 Tip: First generation will download models (~1GB)")
    print("   Models will be saved locally for future use")
else:
    print("⚠️ No local models found - will download from Hugging Face")
    print("💡 Tip: First generation will download models (~1GB)")
    print("   Models will be saved locally for future use")
print(SEPARATOR)

# Print final initialization with nodes list
# print(f"🚀 ChatterBox Voice Extension {VERSION_DISPLAY} loaded with {len(NODE_DISPLAY_NAME_MAPPINGS)} nodes:")
# for node in sorted(NODE_DISPLAY_NAME_MAPPINGS.values()):
#     print(f"   • {node}")
# print(SEPARATOR)
