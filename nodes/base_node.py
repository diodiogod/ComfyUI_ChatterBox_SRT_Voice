"""
Base Node - Common functionality for all ChatterBox Voice nodes
Provides shared methods and standardized interfaces
"""

import torch
import numpy as np
import tempfile
import os
from typing import Dict, Any, Optional, Tuple
import comfy.model_management as model_management

# Use absolute imports that work when loaded via importlib
import os
import sys

# Add parent directory to path for imports
current_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from core.model_manager import model_manager


class BaseChatterBoxNode:
    """
    Base class for all ChatterBox Voice nodes.
    Provides common functionality and standardized interfaces.
    """
    
    # Node metadata that can be overridden by subclasses
    CATEGORY = "ChatterBox Voice"
    FUNCTION = "process"
    
    def __init__(self):
        """Initialize base node with common properties."""
        self.model_manager = model_manager
        self.device = None
        self._temp_files = []  # Track temporary files for cleanup
    
    def __del__(self):
        """Cleanup temporary files when node is destroyed."""
        self.cleanup_temp_files()
    
    def cleanup_temp_files(self):
        """Clean up any temporary files created by the node."""
        for temp_file in self._temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except Exception:
                pass  # Ignore cleanup errors
        self._temp_files.clear()
    
    def resolve_device(self, device: str) -> str:
        """
        Resolve device string to actual device.
        
        Args:
            device: Device specification ('auto', 'cuda', 'cpu')
            
        Returns:
            Resolved device string
        """
        if device == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        return device
    
    def set_seed(self, seed: int):
        """
        Set random seeds for reproducible generation.
        
        Args:
            seed: Random seed value (0 means no seed setting)
        """
        if seed != 0:
            torch.manual_seed(seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed(seed)
            np.random.seed(seed)
    
    def check_interruption(self, operation_name: str = "Generation"):
        """
        Check if processing has been interrupted by ComfyUI.
        
        Args:
            operation_name: Name of the operation being performed
            
        Raises:
            InterruptedError: If processing has been interrupted
        """
        if model_management.interrupt_processing:
            raise InterruptedError(f"{operation_name} interrupted by user")
    
    def handle_reference_audio(self, reference_audio: Optional[Dict[str, Any]], 
                             audio_prompt_path: str = "") -> Optional[str]:
        """
        Handle reference audio input, creating temporary files as needed.
        
        Args:
            reference_audio: Audio tensor from ComfyUI
            audio_prompt_path: Path to audio file on disk
            
        Returns:
            Path to audio file for use with ChatterBox models
        """
        audio_prompt = None
        
        if reference_audio is not None:
            # Create temporary file for reference audio
            temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            temp_file.close()
            
            # Save waveform to temporary file
            waveform = reference_audio["waveform"]
            if waveform.dim() == 3:
                waveform = waveform.squeeze(0)  # Remove batch dimension
            
            import torchaudio
            torchaudio.save(temp_file.name, waveform, reference_audio["sample_rate"])
            
            audio_prompt = temp_file.name
            self._temp_files.append(temp_file.name)
            
        elif audio_prompt_path and os.path.exists(audio_prompt_path):
            audio_prompt = audio_prompt_path
        
        return audio_prompt
    
    def format_audio_output(self, audio_tensor: torch.Tensor, sample_rate: int) -> Dict[str, Any]:
        """
        Format audio tensor for ComfyUI output.
        
        Args:
            audio_tensor: Audio tensor from model
            sample_rate: Sample rate of the audio
            
        Returns:
            Audio dictionary in ComfyUI format
        """
        # Ensure audio has batch dimension
        if audio_tensor.dim() == 1:
            audio_tensor = audio_tensor.unsqueeze(0)  # Add channel dimension
        if audio_tensor.dim() == 2 and audio_tensor.shape[0] != 1:
            # If it's multi-channel, we might need to handle it differently
            # For now, assume it's already in [channels, samples] format
            pass
        
        # Add batch dimension for ComfyUI
        if audio_tensor.dim() == 2:
            audio_tensor = audio_tensor.unsqueeze(0)  # Add batch dimension
        
        return {
            "waveform": audio_tensor,
            "sample_rate": sample_rate
        }
    
    def generate_info_string(self, **kwargs) -> str:
        """
        Generate information string about the processing.
        Can be overridden by subclasses to provide specific info.
        
        Args:
            **kwargs: Information to include in the string
            
        Returns:
            Formatted information string
        """
        info_parts = []
        for key, value in kwargs.items():
            if value is not None:
                info_parts.append(f"{key}: {value}")
        
        return ", ".join(info_parts)
    
    def validate_inputs(self, **inputs) -> Dict[str, Any]:
        """
        Validate and normalize inputs. Can be overridden by subclasses.
        
        Args:
            **inputs: Input parameters to validate
            
        Returns:
            Validated and normalized inputs
        """
        # Base implementation - just return inputs
        # Subclasses can override to add specific validation
        return inputs
    
    def get_model_info(self, model_type: str) -> Dict[str, Any]:
        """
        Get information about loaded models.
        
        Args:
            model_type: Type of model ('tts' or 'vc')
            
        Returns:
            Dictionary with model information
        """
        return {
            "source": self.model_manager.get_model_source(model_type),
            "device": self.device,
            "available": self.model_manager.is_available[model_type],
        }
    
    @classmethod
    def get_input_types_base(cls) -> Dict[str, Dict[str, Any]]:
        """
        Get base input types that are common across nodes.
        Subclasses can extend this.
        
        Returns:
            Base input types dictionary
        """
        return {
            "required": {
                "device": (["auto", "cuda", "cpu"], {"default": "auto"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2**32 - 1}),
            },
            "optional": {
                "reference_audio": ("AUDIO", {"tooltip": "Optional reference audio for voice cloning"}),
                "audio_prompt_path": ("STRING", {"default": "", "tooltip": "Path to audio file on disk"}),
            }
        }
    
    def process_with_error_handling(self, process_func, *args, **kwargs):
        """
        Wrapper for processing functions that provides consistent error handling.
        
        Args:
            process_func: Function to execute
            *args: Arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Result of the function
            
        Raises:
            Various exceptions with improved error messages
        """
        try:
            return process_func(*args, **kwargs)
        except InterruptedError:
            # Re-raise interruption errors as-is
            raise
        except ImportError as e:
            if "ChatterBox" in str(e):
                raise ImportError(
                    f"ChatterBox components not available. Please check installation or add bundled version. "
                    f"Original error: {e}"
                )
            else:
                raise
        except Exception as e:
            # Provide more context for other errors
            import traceback
            error_trace = traceback.format_exc()
            raise RuntimeError(
                f"Node processing failed: {type(e).__name__}: {e}\n"
                f"Traceback:\n{error_trace}"
            ) from e


class BaseTTSNode(BaseChatterBoxNode):
    """
    Base class specifically for TTS nodes with common TTS functionality.
    """
    
    def __init__(self):
        super().__init__()
        self.tts_model = None
    
    def load_tts_model(self, device: str = "auto", force_reload: bool = False):
        """
        Load TTS model using the model manager.
        
        Args:
            device: Target device
            force_reload: Force reload even if cached
            
        Returns:
            Loaded TTS model
        """
        device = self.resolve_device(device)
        self.device = device
        
        self.tts_model = self.model_manager.load_tts_model(device, force_reload)
        return self.tts_model
    
    def generate_tts_audio(self, text: str, audio_prompt: Optional[str] = None,
                          exaggeration: float = 0.5, temperature: float = 0.8,
                          cfg_weight: float = 0.5) -> torch.Tensor:
        """
        Generate TTS audio using the loaded model.
        
        Args:
            text: Text to synthesize
            audio_prompt: Optional audio prompt path
            exaggeration: Exaggeration parameter
            temperature: Temperature parameter
            cfg_weight: CFG weight parameter
            
        Returns:
            Generated audio tensor
        """
        if self.tts_model is None:
            raise RuntimeError("TTS model not loaded. Call load_tts_model() first.")
        
        return self.tts_model.generate(
            text,
            audio_prompt_path=audio_prompt,
            exaggeration=exaggeration,
            temperature=temperature,
            cfg_weight=cfg_weight
        )


class BaseVCNode(BaseChatterBoxNode):
    """
    Base class specifically for Voice Conversion nodes.
    """
    
    def __init__(self):
        super().__init__()
        self.vc_model = None
    
    def load_vc_model(self, device: str = "auto", force_reload: bool = False):
        """
        Load VC model using the model manager.
        
        Args:
            device: Target device
            force_reload: Force reload even if cached
            
        Returns:
            Loaded VC model
        """
        device = self.resolve_device(device)
        self.device = device
        
        self.vc_model = self.model_manager.load_vc_model(device, force_reload)
        return self.vc_model
    
    def convert_voice(self, source_path: str, target_path: str) -> torch.Tensor:
        """
        Perform voice conversion using the loaded model.
        
        Args:
            source_path: Path to source audio
            target_path: Path to target voice audio
            
        Returns:
            Converted audio tensor
        """
        if self.vc_model is None:
            raise RuntimeError("VC model not loaded. Call load_vc_model() first.")
        
        return self.vc_model.generate(source_path, target_voice_path=target_path)