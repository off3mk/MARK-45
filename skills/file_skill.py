"""MARK-45 — Skill: Gestión de Archivos"""
import logging
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("MARK45.Skills.Files")

# Mapa de extensiones a categorías
EXT_CATEGORIES = {
    "imágenes":    {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico"},
    "vídeos":      {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"},
    "audio":       {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"},
    "documentos":  {".pdf", ".docx", ".doc", ".odt", ".rtf", ".txt", ".md"},
    "hojas_calculo": {".xlsx", ".xls", ".csv", ".ods"},
    "presentaciones": {".pptx", ".ppt", ".odp"},
    "código":      {".py", ".js", ".ts", ".html", ".css", ".java", ".cpp", ".c", ".go", ".rs"},
    "comprimidos": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"},
    "ejecutables": {".exe", ".msi", ".bat", ".sh"},
    "datos":       {".json", ".xml", ".yaml", ".yml", ".sql", ".db"},
}


class FileSkill:
    """Utilidades para gestión de archivos."""

    def organize_by_type(self, folder: str) -> Dict:
        """Organizar archivos de una carpeta por tipo."""
        folder = Path(folder)
        if not folder.exists():
            return {"error": f"Carpeta no encontrada: {folder}", "moved": 0}

        moved = 0
        errors = []

        for file in folder.iterdir():
            if not file.is_file():
                continue
            ext = file.suffix.lower()
            category = self._get_category(ext)
            if not category:
                category = "otros"

            dest_dir = folder / category
            dest_dir.mkdir(exist_ok=True)
            dest = dest_dir / file.name

            try:
                if dest.exists():
                    dest = dest_dir / f"{file.stem}_{file.stat().st_mtime:.0f}{file.suffix}"
                shutil.move(str(file), str(dest))
                moved += 1
            except Exception as e:
                errors.append(str(e))

        return {"moved": moved, "errors": errors}

    def search_files(self, query: str, root: Optional[str] = None, max_results: int = 20) -> List[str]:
        """Buscar archivos por nombre."""
        if not root:
            root = os.path.expanduser("~")
        results = []
        query_lower = query.lower()
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                # Saltar carpetas del sistema
                dirnames[:] = [d for d in dirnames if not d.startswith('.') and d not in
                                ['$Recycle.Bin', 'Windows', 'System32', 'AppData']]
                for fname in filenames:
                    if query_lower in fname.lower():
                        results.append(os.path.join(dirpath, fname))
                        if len(results) >= max_results:
                            return results
        except Exception as e:
            logger.debug(f"search_files: {e}")
        return results

    @staticmethod
    def _get_category(ext: str) -> Optional[str]:
        for category, extensions in EXT_CATEGORIES.items():
            if ext in extensions:
                return category
        return None
