# Format Specifications for SmartFileFuzzer

This directory contains JSON format specifications for `FileFuzzer`, enabling content-aware fuzzing of common file formats. Each `format.json` file defines the structure of a file type (e.g., JPEG, ZIP), specifying fields like headers, lengths, and data chunks. These serve two purposes:

1. **Examples**: They demonstrate how to write format specs, helping users create custom ones.
2. **Ready-to-Use**: They allow immediate fuzzing of popular formats without needing to write new specs.

## Usage

- **Location**: Copy a `format.json` file to your `input_dir` (e.g., `~/fawkes/inputs/format.json`) or reference it in `fuzzer_config.json` via the `format_spec` field.
- **Customization**: Modify fields to target specific areas (e.g., increase mutations on length fields).
- **Seed Files**: Provide valid seed files matching the format (e.g., `sample.jpg` for `jpeg.json`) in `input_dir`.

See `file_fuzzer.md` for details on configuring and running `FileFuzzer`.

## Available Formats

### Basic Formats
These provide straightforward specs for common formats, ideal for quick fuzzing or learning:

- `jpeg.json`: JPEG image format.
- `png.json`: PNG image format.
- `svg.json`: SVG vector graphics format.
- `pdf.json`: PDF document format.
- `doc.json`: Legacy Microsoft Word (DOC) format.
- `docx.json`: Modern Microsoft Word (DOCX) format.
- `mp3.json`: MP3 audio format.
- `mp4.json`: MP4 video container format.

### Advanced Formats
These are highly detailed specs for complex formats, showcasing `FileFuzzer`’s capabilities for deep fuzzing:

- `zip_advanced.json`: ZIP archive format, with multiple file entries, central directory, and extra fields.
- `targz_advanced.json`: TAR.GZ archive format, with GZIP compression and multiple TAR entries.

## Format Details

### ZIP (Advanced) (`zip_advanced.json`)

ZIP is a compressed archive format with local file headers, file data, a central directory, and an end-of-central-directory (EOCD) record. This advanced spec models an archive with two files, including extra fields and CRCs, to enable deep fuzzing of parsers.

```json
{
  "format_name": "zip_advanced",
  "fields": [
    {
      "name": "local_header1_signature",
      "offset": 0,
      "length": 4,
      "type": "fixed",
      "value": "\x50\x4B\x03\x04"
    },
    {
      "name": "local_header1_version",
      "offset": 4,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "local_header1_flags",
      "offset": 6,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "local_header1_compression",
      "offset": 8,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "local_header1_mtime",
      "offset": 10,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "local_header1_mdate",
      "offset": 12,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "local_header1_crc",
      "offset": 14,
      "length": 4,
      "type": "crc32",
      "covers": ["file1_data"]
    },
    {
      "name": "local_header1_compressed_size",
      "offset": 18,
      "length": 4,
      "type": "uint32",
      "controls": "file1_data"
    },
    {
      "name": "local_header1_uncompressed_size",
      "offset": 22,
      "length": 4,
      "type": "uint32"
    },
    {
      "name": "local_header1_filename_length",
      "offset": 26,
      "length": 2,
      "type": "uint16",
      "controls": "file1_name"
    },
    {
      "name": "local_header1_extra_length",
      "offset": 28,
      "length": 2,
      "type": "uint16",
      "controls": "file1_extra"
    },
    {
      "name": "file1_name",
      "offset": 30,
      "length_field": "local_header1_filename_length",
      "type": "string"
    },
    {
      "name": "file1_extra",
      "offset": null,
      "length_field": "local_header1_extra_length",
      "type": "bytes"
    },
    {
      "name": "file1_data",
      "offset": null,
      "length_field": "local_header1_compressed_size",
      "type": "bytes"
    },
    {
      "name": "local_header2_signature",
      "offset": null,
      "length": 4,
      "type": "fixed",
      "value": "\x50\x4B\x03\x04"
    },
    {
      "name": "local_header2_version",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "local_header2_flags",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "local_header2_compression",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "local_header2_mtime",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "local_header2_mdate",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "local_header2_crc",
      "offset": null,
      "length": 4,
      "type": "crc32",
      "covers": ["file2_data"]
    },
    {
      "name": "local_header2_compressed_size",
      "offset": null,
      "length": 4,
      "type": "uint32",
      "controls": "file2_data"
    },
    {
      "name": "local_header2_uncompressed_size",
      "offset": null,
      "length": 4,
      "type": "uint32"
    },
    {
      "name": "local_header2_filename_length",
      "offset": null,
      "length": 2,
      "type": "uint16",
      "controls": "file2_name"
    },
    {
      "name": "local_header2_extra_length",
      "offset": null,
      "length": 2,
      "type": "uint16",
      "controls": "file2_extra"
    },
    {
      "name": "file2_name",
      "offset": null,
      "length_field": "local_header2_filename_length",
      "type": "string"
    },
    {
      "name": "file2_extra",
      "offset": null,
      "length_field": "local_header2_extra_length",
      "type": "bytes"
    },
    {
      "name": "file2_data",
      "offset": null,
      "length_field": "local_header2_compressed_size",
      "type": "bytes"
    },
    {
      "name": "central_dir1_signature",
      "offset": null,
      "length": 4,
      "type": "fixed",
      "value": "\x50\x4B\x01\x02"
    },
    {
      "name": "central_dir1_version_made",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "central_dir1_version_needed",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "central_dir1_flags",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "central_dir1_compression",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "central_dir1_mtime",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "central_dir1_mdate",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "central_dir1_crc",
      "offset": null,
      "length": 4,
      "type": "crc32",
      "covers": ["file1_data"]
    },
    {
      "name": "central_dir1_compressed_size",
      "offset": null,
      "length": 4,
      "type": "uint32"
    },
    {
      "name": "central_dir1_uncompressed_size",
      "offset": null,
      "length": 4,
      "type": "uint32"
    },
    {
      "name": "central_dir1_filename_length",
      "offset": null,
      "length": 2,
      "type": "uint16",
      "controls": "central_dir1_filename"
    },
    {
      "name": "central_dir1_extra_length",
      "offset": null,
      "length": 2,
      "type": "uint16",
      "controls": "central_dir1_extra"
    },
    {
      "name": "central_dir1_comment_length",
      "offset": null,
      "length": 2,
      "type": "uint16",
      "controls": "central_dir1_comment"
    },
    {
      "name": "central_dir1_disk_number",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "central_dir1_internal_attrs",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "central_dir1_external_attrs",
      "offset": null,
      "length": 4,
      "type": "uint32"
    },
    {
      "name": "central_dir1_offset",
      "offset": null,
      "length": 4,
      "type": "uint32"
    },
    {
      "name": "central_dir1_filename",
      "offset": null,
      "length_field": "central_dir1_filename_length",
      "type": "string"
    },
    {
      "name": "central_dir1_extra",
      "offset": null,
      "length_field": "central_dir1_extra_length",
      "type": "bytes"
    },
    {
      "name": "central_dir1_comment",
      "offset": null,
      "length_field": "central_dir1_comment_length",
      "type": "string"
    },
    {
      "name": "central_dir2_signature",
      "offset": null,
      "length": 4,
      "type": "fixed",
      "value": "\x50\x4B\x01\x02"
    },
    {
      "name": "central_dir2_version_made",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "central_dir2_version_needed",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "central_dir2_flags",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "central_dir2_compression",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "central_dir2_mtime",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "central_dir2_mdate",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "central_dir2_crc",
      "offset": null,
      "length": 4,
      "type": "crc32",
      "covers": ["file2_data"]
    },
    {
      "name": "central_dir2_compressed_size",
      "offset": null,
      "length": 4,
      "type": "uint32"
    },
    {
      "name": "central_dir2_uncompressed_size",
      "offset": null,
      "length": 4,
      "type": "uint32"
    },
    {
      "name": "central_dir2_filename_length",
      "offset": null,
      "length": 2,
      "type": "uint16",
      "controls": "central_dir2_filename"
    },
    {
      "name": "central_dir2_extra_length",
      "offset": null,
      "length": 2,
      "type": "uint16",
      "controls": "central_dir2_extra"
    },
    {
      "name": "central_dir2_comment_length",
      "offset": null,
      "length": 2,
      "type": "uint16",
      "controls": "central_dir2_comment"
    },
    {
      "name": "central_dir2_disk_number",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "central_dir2_internal_attrs",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "central_dir2_external_attrs",
      "offset": null,
      "length": 4,
      "type": "uint32"
    },
    {
      "name": "central_dir2_offset",
      "offset": null,
      "length": 4,
      "type": "uint32"
    },
    {
      "name": "central_dir2_filename",
      "offset": null,
      "length_field": "central_dir2_filename_length",
      "type": "string"
    },
    {
      "name": "central_dir2_extra",
      "offset": null,
      "length_field": "central_dir2_extra_length",
      "type": "bytes"
    },
    {
      "name": "central_dir2_comment",
      "offset": null,
      "length_field": "central_dir2_comment_length",
      "type": "string"
    },
    {
      "name": "eocd_signature",
      "offset": null,
      "length": 4,
      "type": "fixed",
      "value": "\x50\x4B\x05\x06"
    },
    {
      "name": "eocd_disk_number",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "eocd_start_disk",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "eocd_entries_disk",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "eocd_total_entries",
      "offset": null,
      "length": 2,
      "type": "uint16"
    },
    {
      "name": "eocd_central_dir_size",
      "offset": null,
      "length": 4,
      "type": "uint32"
    },
    {
      "name": "eocd_central_dir_offset",
      "offset": null,
      "length": 4,
      "type": "uint32"
    },
    {
      "name": "eocd_comment_length",
      "offset": null,
      "length": 2,
      "type": "uint16",
      "controls": "eocd_comment"
    },
    {
      "name": "eocd_comment",
      "offset": null,
      "length_field": "eocd_comment_length",
      "type": "string"
    }
  ]
}
```

**Notes**:
- **Structure**: Models two files with local headers (`local_header1`, `local_header2`), central directory entries (`central_dir1`, `central_dir2`), and EOCD.
- **Fields**:
  - Local headers: Signature, version, flags, compression (0=stored, 8=deflate), timestamps, CRC, sizes, filename, extra data.
  - Central directory: Repeats local header info, adds disk numbers, attributes, offsets, comments.
  - EOCD: Tracks total entries, central directory size/offset, archive comment.
- **Dependencies**:
  - `compressed_size` controls `file_data`.
  - `filename_length` controls `file_name`.
  - `crc` covers `file_data`.
- **Fuzzing Targets**:
  - Oversized `compressed_size`/`uncompressed_size` for buffer overflows.
  - Corrupt `crc` for validation errors.
  - Invalid `compression` (e.g., 99) for parser crashes.
  - Long `file_name` or `extra` for memory issues.
  - Mismatched `central_dir_offset` or `total_entries` for directory parsing bugs.
- **Extensibility**: Add more `local_headerN` and `central_dirN` for larger archives.
- **Complexity**: 50+ fields capture ZIP’s full structure, ideal for deep coverage.

### TAR.GZ (Advanced) (`targz_advanced.json`)

TAR.GZ is a TAR archive (concatenated file entries with headers) compressed with GZIP. This spec models a GZIP header and a TAR archive with two file entries, including headers, data, and padding.

```json
{
  "format_name": "targz_advanced",
  "fields": [
    {
      "name": "gzip_id",
      "offset": 0,
      "length": 2,
      "type": "fixed",
      "value": "\x1F\x8B"
    },
    {
      "name": "gzip_compression",
      "offset": 2,
      "length": 1,
      "type": "uint8"
    },
    {
      "name": "gzip_flags",
      "offset": 3,
      "length": 1,
      "type": "uint8"
    },
    {
      "name": "gzip_mtime",
      "offset": 4,
      "length": 4,
      "type": "uint32"
    },
    {
      "name": "gzip_xfl",
      "offset": 8,
      "length": 1,
      "type": "uint8"
    },
    {
      "name": "gzip_os",
      "offset": 9,
      "length": 1,
      "type": "uint8"
    },
    {
      "name": "gzip_extra_length",
      "offset": 10,
      "length": 2,
      "type": "uint16",
      "controls": "gzip_extra"
    },
    {
      "name": "gzip_extra",
      "offset": 12,
      "length_field": "gzip_extra_length",
      "type": "bytes"
    },
    {
      "name": "tar_header1_name",
      "offset": null,
      "length": 100,
      "type": "string"
    },
    {
      "name": "tar_header1_mode",
      "offset": null,
      "length": 8,
      "type": "string"
    },
    {
      "name": "tar_header1_uid",
      "offset": null,
      "length": 8,
      "type": "string"
    },
    {
      "name": "tar_header1_gid",
      "offset": null,
      "length": 8,
      "type": "string"
    },
    {
      "name": "tar_header1_size",
      "offset": null,
      "length": 12,
      "type": "string",
      "controls": "tar_file1_data"
    },
    {
      "name": "tar_header1_mtime",
      "offset": null,
      "length": 12,
      "type": "string"
    },
    {
      "name": "tar_header1_checksum",
      "offset": null,
      "length": 8,
      "type": "string",
      "covers": [
        "tar_header1_name",
        "tar_header1_mode",
        "tar_header1_uid",
        "tar_header1_gid",
        "tar_header1_size",
        "tar_header1_mtime",
        "tar_header1_typeflag",
        "tar_header1_linkname",
        "tar_header1_magic",
        "tar_header1_version",
        "tar_header1_uname",
        "tar_header1_gname",
        "tar_header1_devmajor",
        "tar_header1_devminor",
        "tar_header1_prefix"
      ]
    },
    {
      "name": "tar_header1_typeflag",
      "offset": null,
      "length": 1,
      "type": "string"
    },
    {
      "name": "tar_header1_linkname",
      "offset": null,
      "length": 100,
      "type": "string"
    },
    {
      "name": "tar_header1_magic",
      "offset": null,
      "length": 6,
      "type": "fixed",
      "value": "ustar "
    },
    {
      "name": "tar_header1_version",
      "offset": null,
      "length": 2,
      "type": "string"
    },
    {
      "name": "tar_header1_uname",
      "offset": null,
      "length": 32,
      "type": "string"
    },
    {
      "name": "tar_header1_gname",
      "offset": null,
      "length": 32,
      "type": "string"
    },
    {
      "name": "tar_header1_devmajor",
      "offset": null,
      "length": 8,
      "type": "string"
    },
    {
      "name": "tar_header1_devminor",
      "offset": null,
      "length": 8,
      "type": "string"
    },
    {
      "name": "tar_header1_prefix",
      "offset": null,
      "length": 155,
      "type": "string"
    },
    {
      "name": "tar_file1_data",
      "offset": null,
      "length_field": "tar_header1_size",
      "type": "bytes"
    },
    {
      "name": "tar_file1_padding",
      "offset": null,
      "length": 0,
      "type": "bytes"
    },
    {
      "name": "tar_header2_name",
      "offset": null,
      "length": 100,
      "type": "string"
    },
    {
      "name": "tar_header2_mode",
      "offset": null,
      "length": 8,
      "type": "string"
    },
    {
      "name": "tar_header2_uid",
      "offset": null,
      "length": 8,
      "type": "string"
    },
    {
      "name": "tar_header2_gid",
      "offset": null,
      "length": 8,
      "type": "string"
    },
    {
      "name": "tar_header2_size",
      "offset": null,
      "length": 12,
      "type": "string",
      "controls": "tar_file2_data"
    },
    {
      "name": "tar_header2_mtime",
      "offset": null,
      "length": 12,
      "type": "string"
    },
    {
      "name": "tar_header2_checksum",
      "offset": null,
      "length": 8,
      "type": "string",
      "covers": [
        "tar_header2_name",
        "tar_header2_mode",
        "tar_header2_uid",
        "tar_header2_gid",
        "tar_header2_size",
        "tar_header2_mtime",
        "tar_header2_typeflag",
        "tar_header2_linkname",
        "tar_header2_magic",
        "tar_header2_version",
        "tar_header2_uname",
        "tar_header2_gname",
        "tar_header2_devmajor",
        "tar_header2_devminor",
        "tar_header2_prefix"
      ]
    },
    {
      "name": "tar_header2_typeflag",
      "offset": null,
      "length": 1,
      "type": "string"
    },
    {
      "name": "tar_header2_linkname",
      "offset": null,
      "length": 100,
      "type": "string"
    },
    {
      "name": "tar_header2_magic",
      "offset": null,
      "length": 6,
      "type": "fixed",
      "value": "ustar "
    },
    {
      "name": "tar_header2_version",
      "offset": null,
      "length": 2,
      "type": "string"
    },
    {
      "name": "tar_header2_uname",
      "offset": null,
      "length": 32,
      "type": "string"
    },
    {
      "name": "tar_header2_gname",
      "offset": null,
      "length": 32,
      "type": "string"
    },
    {
      "name": "tar_header2_devmajor",
      "offset": null,
      "length": 8,
      "type": "string"
    },
    {
      "name": "tar_header2_devminor",
      "offset": null,
      "length": 8,
      "type": "string"
    },
    {
      "name": "tar_header2_prefix",
      "offset": null,
      "length": 155,
      "type": "string"
    },
    {
      "name": "tar_file2_data",
      "offset": null,
      "length_field": "tar_header2_size",
      "type": "bytes"
    },
    {
      "name": "tar_file2_padding",
      "offset": null,
      "length": 0,
      "type": "bytes"
    },
    {
      "name": "gzip_crc",
      "offset": null,
      "length": 4,
      "type": "crc32",
      "covers": [
        "tar_header1_name",
        "tar_header1_mode",
        "tar_header1_uid",
        "tar_header1_gid",
        "tar_header1_size",
        "tar_header1_mtime",
        "tar_header1_checksum",
        "tar_header1_typeflag",
        "tar_header1_linkname",
        "tar_header1_magic",
        "tar_header1_version",
        "tar_header1_uname",
        "tar_header1_gname",
        "tar_header1_devmajor",
        "tar_header1_devminor",
        "tar_header1_prefix",
        "tar_file1_data",
        "tar_file1_padding",
        "tar_header2_name",
        "tar_header2_mode",
        "tar_header2_uid",
        "tar_header2_gid",
        "tar_header2_size",
        "tar_header2_mtime",
        "tar_header2_checksum",
        "tar_header2_typeflag",
        "tar_header2_linkname",
        "tar_header2_magic",
        "tar_header2_version",
        "tar_header2_uname",
        "tar_header2_gname",
        "tar_header2_devmajor",
        "tar_header2_devminor",
        "tar_header2_prefix",
        "tar_file2_data",
        "tar_file2_padding"
      ]
    },
    {
      "name": "gzip_size",
      "offset": null,
      "length": 4,
      "type": "uint32"
    }
  ]
}
```

**Notes**:
- **Structure**: GZIP wrapper (ID, flags, extra fields) around a TAR archive with two file entries (`tar_header1`, `tar_header2`), each with metadata, data, and padding.
- **Fields**:
  - GZIP: ID (`0x1F8B`), compression method (8=deflate), flags, timestamps, OS, extra fields.
  - TAR headers: Name, mode, UID/GID, size (octal string), timestamps, checksum, typeflag, linkname, ustar magic, user/group names, device numbers, prefix.
  - TAR data: File contents, sized by `size` field.
  - Padding: Aligns to 512-byte blocks, mutated for boundary errors.
  - GZIP footer: CRC and uncompressed size.
- **Dependencies**:
  - `tar_headerN_size` controls `tar_fileN_data` (parsed as octal).
  - `tar_headerN_checksum` covers all header fields.
  - `gzip_extra_length` controls `gzip_extra`.
  - `gzip_crc` covers the entire TAR archive.
- **Fuzzing Targets**:
  - Oversized `tar_headerN_size` for overflows.
  - Corrupt `tar_headerN_checksum` or `gzip_crc` for validation failures.
  - Invalid `gzip_compression` (e.g., 99) or `flags` for parser crashes.
  - Long `tar_headerN_name` or `prefix` for memory issues.
  - Large `tar_fileN_data` or malformed `tar_fileN_padding` for decompression errors.
- **Extensibility**: Add more `tar_headerN` for additional files.
- **Complexity**: 40+ fields, nested GZIP/TAR structure, multiple checksums, and padding make this a deep spec.
