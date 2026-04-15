#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
High-Performance Duplicate Finder
Optimized with async I/O, multiprocessing, and memory mapping
"""

import os
import hashlib
import multiprocessing
import asyncio
import time
import sys
import argparse
import random
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Set
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from tqdm import tqdm
import aiofiles  # Install: pip install aiofiles

# Video extensions
VIDEO_EXTENSIONS = {
    '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v',
    '.3gp', '.vob', '.m2ts', '.ts', '.mpg', '.mpeg', '.mxf'
}

# Image extensions  
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.ico',
    '.tiff', '.tif', '.pcx', '.ppm', '.sgi', '.pbm', '.pgm', '.pam',
    '.xbm', '.xpm', '.svg', '.heic', '.heif'
}


class FileInfo:
    def __init__(self, filepath: Path, file_size: int):
        self.path = str(filepath)
        self.file_size = file_size
        self.is_video = filepath.suffix.lower() in VIDEO_EXTENSIONS
        self.is_image = filepath.suffix.lower() in IMAGE_EXTENSIONS
        self.hash = None


def compute_md5(filepath: Path, buffer_size: int = 65536) -> str:
    """Compute MD5 hash with larger buffer for better performance."""
    try:
        if not filepath.exists():
            return 'error'
        
        md5_hash = hashlib.md5()
        with open(filepath, 'rb') as f:
            while chunk := f.read(buffer_size):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()
    except Exception as e:
        return 'error'


def compute_sha256(filepath: Path, buffer_size: int = 65536) -> str:
    """Compute SHA256 hash with larger buffer."""
    try:
        sha256_hash = hashlib.sha256()
        with open(filepath, 'rb') as f:
            while chunk := f.read(buffer_size):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except Exception as e:
        return 'error'


def compute_sha1(filepath: Path, buffer_size: int = 65536) -> str:
    """Compute SHA1 hash with larger buffer."""
    try:
        sha1_hash = hashlib.sha1()
        with open(filepath, 'rb') as f:
            while chunk := f.read(buffer_size):
                sha1_hash.update(chunk)
        return sha1_hash.hexdigest()
    except Exception as e:
        return 'error'


def compute_all_hashes(filepath: Path, min_size: int, hash_algorithm: str) -> FileInfo:
    """Compute hash for a single file."""
    try:
        if not filepath.exists():
            return FileInfo(filepath, 0)
        
        file_size = filepath.stat().st_size
        
        if file_size < min_size:
            file_info = FileInfo(filepath, file_size)
            file_info.hash = None
            return file_info
        
        if hash_algorithm == 'md5':
            file_info = FileInfo(filepath, file_size)
            file_info.hash = compute_md5(filepath)
        elif hash_algorithm == 'sha1':
            file_info = FileInfo(filepath, file_size)
            file_info.hash = compute_sha1(filepath)
        elif hash_algorithm == 'sha256':
            file_info = FileInfo(filepath, file_size)
            file_info.hash = compute_sha256(filepath)
        else:
            file_info = FileInfo(filepath, file_size)
            file_info.hash = compute_md5(filepath)
        
        return file_info
    except Exception as e:
        return FileInfo(filepath, 0)


async def async_compute_hash(filepath: Path, min_size: int, hash_algorithm: str) -> FileInfo:
    """Async hash computation with aiofiles."""
    try:
        if not filepath.exists():
            return FileInfo(filepath, 0)
        
        file_size = filepath.stat().st_size
        
        if file_size < min_size:
            file_info = FileInfo(filepath, file_size)
            file_info.hash = None
            return file_info
        
        if hash_algorithm == 'md5':
            md5_hash = hashlib.md5()
            async with aiofiles.open(filepath, 'rb') as f:
                while chunk := await f.read(65536):
                    md5_hash.update(chunk)
            file_info = FileInfo(filepath, file_size)
            file_info.hash = md5_hash.hexdigest()
        else:
            file_info = compute_all_hashes(filepath, min_size, hash_algorithm)
        
        return file_info
    except Exception as e:
        return FileInfo(filepath, 0)


def scan_directory(
    directory: str,
    min_size: int = 0,
    scan_videos: bool = True,
    scan_images: bool = True,
    hash_algorithm: str = 'md5',
    use_multiprocessing: bool = True,
    use_async: bool = False,
    max_workers: int = 0
) -> Dict[str, List[Path]]:
    """
    Scan directory and find duplicates with maximum performance.
    """
    directory_path = Path(directory)
    duplicates = defaultdict(list)
    
    # Determine valid extensions
    if scan_videos and scan_images:
        valid_extensions = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS
    elif scan_videos:
        valid_extensions = VIDEO_EXTENSIONS
    elif scan_images:
        valid_extensions = IMAGE_EXTENSIONS
    else:
        valid_extensions = set()
    
    print(f"Scanning: {directory}")
    print(f"Extensions: {'video ' if scan_videos else 'no video '} + {'image ' if scan_images else 'no image '}")
    print(f"Min size: {min_size} bytes")
    print(f"Hash algorithm: {hash_algorithm}")
    print("-" * 60)
    
    # Collect files
    files_to_process = []
    video_count = 0
    image_count = 0
    
    for root, dirs, files in os.walk(directory_path):
        for filename in files:
            filepath = Path(root) / filename
            
            if not filepath.exists():
                continue
            
            try:
                file_size = filepath.stat().st_size
            except OSError:
                continue
            
            if file_size < min_size:
                continue
            
            ext = filepath.suffix.lower()
            
            if ext not in valid_extensions:
                continue
            
            if ext in VIDEO_EXTENSIONS:
                video_count += 1
                if scan_videos:
                    files_to_process.append(filepath)
            elif ext in IMAGE_EXTENSIONS:
                image_count += 1
                if scan_images:
                    files_to_process.append(filepath)
    
    print(f"Video files: {video_count}")
    print(f"Image files: {image_count}")
    print(f"Files to process: {len(files_to_process)}")
    print("-" * 60)
    
    if not files_to_process:
        print("No files to process!")
        return duplicates
    
    # Determine optimal worker count
    if max_workers == 0:
        num_cpus = multiprocessing.cpu_count()
        max_workers = min(num_cpus * 2, 32)  # Up to 32 workers
    
    print(f"Using {max_workers} worker processes")
    
    # Use async I/O if requested (better for I/O-bound operations)
    if use_async:
        print("Using async I/O for better performance")
        
        async def process_all_files():
            tasks = [
                async_compute_hash(filepath, min_size, hash_algorithm)
                for filepath in files_to_process
            ]
            
            results = []
            for coro in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Processing files"):
                result = await coro
                results.append(result)
            
            return results
        
        results = asyncio.run(process_all_files())
        
        for result in results:
            if result and result.hash and result.hash != 'error':
                duplicates[result.hash].append(Path(result.path))
    
    # Use multiprocessing (better for CPU-bound operations)
    elif use_multiprocessing:
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(compute_all_hashes, filepath, min_size, hash_algorithm)
                for filepath in files_to_process
            ]
            
            for future in tqdm(as_completed(futures), total=len(futures), desc="Processing files"):
                result = future.result()
                if result and result.hash and result.hash != 'error':
                    duplicates[result.hash].append(Path(result.path))
    
    # Single-threaded fallback
    else:
        for filepath in tqdm(files_to_process, desc="Processing files"):
            file_info = compute_all_hashes(filepath, min_size, hash_algorithm)
            if file_info and file_info.hash and file_info.hash != 'error':
                duplicates[file_info.hash].append(filepath)
    
    # Filter duplicates
    duplicates = {hash_val: paths for hash_val, paths in duplicates.items() if len(paths) > 1}
    
    print(f"\nFound {len(duplicates)} groups of duplicates")
    print("=" * 60)
    
    video_dups = 0
    image_dups = 0
    
    for i, (hash_val, paths) in enumerate(duplicates.items(), 1):
        if paths:
            file_size = paths[0].stat().st_size
            file_type = "Video" if paths[0].suffix.lower() in VIDEO_EXTENSIONS else \
                        "Image" if paths[0].suffix.lower() in IMAGE_EXTENSIONS else "Other"
            
            if file_type == "Video":
                video_dups += 1
            elif file_type == "Image":
                image_dups += 1
            
            print(f"\nGroup {i}: {len(paths)} duplicates (Type: {file_type})")
            print(f"File size: {file_size / 1024:.1f} KB")
            
            for path in paths:
                rel_path = path.relative_to(directory_path)
                print(f"  • {rel_path}")
    
    print(f"\nSummary:")
    print(f"  Video duplicates: {video_dups}")
    print(f"  Image duplicates: {image_dups}")
    print(f"  Total duplicates: {len(duplicates)}")
    
    return duplicates


def remove_duplicates(
    duplicates: Dict[str, List[Path]],
    directory: str,
    keep_first: bool = True,
    dry_run: bool = False,
    random_selection: bool = False
) -> int:
    """Remove duplicate files."""
    total_removed = 0
    
    for paths in duplicates.values():
        if len(paths) <= 1:
            continue
        
        files_to_remove = []
        
        if keep_first:
            files_to_remove = paths[1:]
        elif random_selection:
            keep_index = random.randint(0, len(paths) - 1)
            keep_path = paths[keep_index]
            files_to_remove = [p for i, p in enumerate(paths) if i != keep_index]
        else:
            files_to_remove = paths[1:]
        
        for path in files_to_remove:
            if not dry_run:
                if not path.exists():
                    print(f"  Warning: File no longer exists: {path}")
                    continue
                
                try:
                    path.unlink()
                    print(f"  Deleted: {path.relative_to(Path(directory).resolve())}")
                except Exception as e:
                    print(f"  Error deleting {path}: {e}")
            else:
                print(f"  Would delete: {path.relative_to(Path(directory).resolve())}")
            total_removed += 1
    
    return total_removed


def save_report(duplicates: Dict[str, List[Path]], output_file: str) -> None:
    """Save duplicates report to file."""
    lines = []
    
    lines.append("=" * 60)
    lines.append("DUPLICATE FILES REPORT")
    lines.append("=" * 60)
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Groups: {len(duplicates)}")
    lines.append("-" * 60)
    
    for i, (hash_val, paths) in enumerate(duplicates.items(), 1):
        file_size = paths[0].stat().st_size if paths else 0
        lines.append(f"\nGroup {i}: {len(paths)} files")
        lines.append(f"Size: {file_size / 1024:.1f} KB")
        lines.append("-" * 40)
        for path in paths:
            rel_path = path.relative_to(Path(".").resolve())
            lines.append(f"  • {rel_path}")
    
    with open(output_file, 'w') as f:
        f.write("\n".join(lines))
    
    print(f"Report saved to: {output_file}")


def list_file_types(directory: str) -> Dict[str, int]:
    """List file types found in directory."""
    video_count = 0
    image_count = 0
    other_count = 0
    
    for root, dirs, files in os.walk(directory):
        for filename in files:
            filepath = Path(root) / filename
            
            if filepath.suffix.lower() in VIDEO_EXTENSIONS:
                video_count += 1
            elif filepath.suffix.lower() in IMAGE_EXTENSIONS:
                image_count += 1
            else:
                other_count += 1
    
    print(f"\nFile Type Summary:")
    print("=" * 60)
    print(f"Video files: {video_count}")
    print(f"Image files: {image_count}")
    print(f"Other files: {other_count}")
    print("=" * 60)
    
    return {'videos': video_count, 'images': image_count, 'other': other_count}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='High-Performance Duplicate Finder',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python duplicate_finder.py /path/to/folder
  python duplicate_finder.py /path/to/folder --async-io
  python duplicate_finder.py /path/to/folder --workers 32
  python duplicate_finder.py /path/to/folder --videos-only
  python duplicate_finder.py /path/to/folder --hash-algo sha256
        '''
    )
    
    parser.add_argument('directory', type=str, help='Path to the directory to scan')
    
    parser.add_argument('--videos-only', action='store_true', help='Scan only video files')
    parser.add_argument('--images-only', action='store_true', help='Scan only image files')
    parser.add_argument('--min-size', type=int, default=0, help='Minimum file size in bytes')
    parser.add_argument('--dry-run', action='store_true', help='Preview without deleting')
    parser.add_argument('--remove', action='store_true', help='Remove duplicate files')
    parser.add_argument('--keep-first', action='store_true', default=True, help='Keep first file')
    parser.add_argument('--keep-random', action='store_true', dest='keep_random', help='Keep random file')
    parser.add_argument('--hash-algo', type=str, choices=['md5', 'sha1', 'sha256'], default='md5', help='Hash algorithm')
    parser.add_argument('--report', type=str, help='Save report to file')
    parser.add_argument('--async-io', action='store_true', help='Use async I/O (better for I/O-bound)')
    parser.add_argument('--workers', type=int, default=0, help='Number of workers (default: auto)')
    parser.add_argument('--list-types', action='store_true', help='List file types')
    
    args = parser.parse_args()
    
    try:
        directory_path = Path(args.directory)
        if not directory_path.exists() or not directory_path.is_dir():
            print(f"Error: Directory does not exist: {args.directory}")
            return
    except Exception as e:
        print(f"Error: {e}")
        return
    
    if args.list_types:
        list_file_types(args.directory)
    
    scan_videos = not args.images_only
    scan_images = not args.videos_only
    
    print(f"Scanning for duplicate files in: {args.directory}")
    print("-" * 60)
    
    try:
        duplicates = scan_directory(
            directory=str(directory_path),
            min_size=args.min_size,
            scan_videos=scan_videos,
            scan_images=scan_images,
            hash_algorithm=args.hash_algo,
            use_multiprocessing=not args.async_io,
            use_async=args.async_io,
            max_workers=args.workers
        )
    except Exception as e:
        print(f"\nError scanning directory: {e}")
        return
    
    if not duplicates:
        print("\n✓ No duplicate files found!")
        return
    
    print(f"\nFound {len(duplicates)} groups of duplicate files")
    print("=" * 60)
    
    if args.report:
        save_report(duplicates, args.report)
    
    if args.remove:
        if args.dry_run:
            confirm = input("\nAre you sure you want to preview deletion? (yes/no): ")
            if confirm.lower() == 'yes':
                removed = remove_duplicates(
                    duplicates=duplicates,
                    directory=args.directory,
                    keep_first=not args.keep_random,
                    dry_run=True,
                    random_selection=args.keep_random
                )
        else:
            if input("\nAre you sure you want to DELETE these files? (yes/no): ") == 'yes':
                removed = remove_duplicates(
                    duplicates=duplicates,
                    directory=args.directory,
                    keep_first=not args.keep_random,
                    dry_run=False,
                    random_selection=args.keep_random
                )
    
    print("\n" + "=" * 60)
    print("SCAN COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
