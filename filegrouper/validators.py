"""Input validation utilities for CLI and GUI."""

from pathlib import Path
from typing import Optional


class ValidationError(ValueError):
    """Raised when input validation fails."""
    pass


def validate_source_path(path: Optional[str]) -> Path:
    """Validate source directory path.
    
    Args:
        path: Path string to validate
        
    Returns:
        Validated Path object
        
    Raises:
        ValidationError: If path is invalid
    """
    if not path:
        raise ValidationError("Kaynak klasör seçmeden başlayamazsın.")
    
    p = Path(path)
    
    if not p.exists():
        raise ValidationError(f"Kaynak klasör bulunamadı: {path}")
    
    if not p.is_dir():
        raise ValidationError(f"Kaynak bir klasör olmalı: {path}")
    
    return p.resolve()


def validate_target_path(path: Optional[str], scope_includes_grouping: bool) -> Optional[Path]:
    """Validate target directory path.
    
    Args:
        path: Path string to validate (can be None for dedupe-only)
        scope_includes_grouping: Whether operation includes grouping
        
    Returns:
        Validated Path object or None
        
    Raises:
        ValidationError: If path is invalid
    """
    if scope_includes_grouping:
        if not path:
            raise ValidationError("Gruplama için hedef klasör seçmek zorunlu.")
        
        p = Path(path)
        
        if not p.exists():
            raise ValidationError(f"Hedef klasör bulunamadı: {path}")
        
        if not p.is_dir():
            raise ValidationError(f"Hedef bir klasör olmalı: {path}")
        
        return p.resolve()
    
    return None


def validate_paths_separated(source: Path, target: Optional[Path]) -> None:
    """Validate that source and target are different.
    
    Args:
        source: Source path (resolved)
        target: Target path (resolved) or None
        
    Raises:
        ValidationError: If paths are not properly separated
    """
    if target is None:
        return
    
    # Compare resolved paths
    source_resolved = source.resolve()
    target_resolved = target.resolve()
    
    if source_resolved == target_resolved:
        raise ValidationError("Kaynak ve hedef klasör aynı olamaz.")
    
    # Check if target is subdirectory of source
    try:
        target_resolved.relative_to(source_resolved)
        # If we get here, target is inside source
        raise ValidationError("Hedef klasör kaynak klasörün içinde olamaz.")
    except ValidationError:
        # Re-raise our ValidationError
        raise
    except ValueError:
        # Good: target is NOT inside source (ValueError from relative_to)
        pass


def validate_similarity_max_distance(value: int) -> int:
    """Validate max distance for image similarity.
    
    Args:
        value: Max hamming distance
        
    Returns:
        Validated value
        
    Raises:
        ValidationError: If value is invalid
    """
    if not isinstance(value, int):
        try:
            value = int(value)
        except (ValueError, TypeError):
            raise ValidationError(f"Max distance must be integer, got: {value}")
    
    if value < 0:
        raise ValidationError(f"Max distance must be >= 0, got: {value}")
    
    if value > 64:  # Max for 64-bit hash
        raise ValidationError(f"Max distance must be <= 64, got: {value}")
    
    return value
