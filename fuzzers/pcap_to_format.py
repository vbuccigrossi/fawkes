#!/usr/bin/env python3
"""
pcap_to_format.py

FEATURES:
- Multi-packet support: unify fields from multiple packets or produce one file per packet.
- Custom heuristics for checksums, length fields, etc.
- DHCP "options" example for repeated subfields.
- Flexible command-line interface.

USAGE EXAMPLE:
    python pcap_to_formatjson.py traffic.pcap DHCP --mode=unified --out dhcp_unified.json

Requires scapy:
    pip install scapy

"""

import argparse
import json
import logging
import os
from scapy.all import rdpcap, Packet
from scapy.fields import (
    BitField, ByteField, ShortField, IntField,
    XShortField, XIntField, FieldLenField,
    StrField, FieldListField
)

logging.getLogger("scapy.runtime").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# If you want console output, uncomment:
# console = logging.StreamHandler()
# console.setLevel(logging.INFO)
# logger.addHandler(console)


def guess_fuzzer_type(field_name: str, field_class, field_value) -> str:
    """
    Heuristic to guess the fuzzer's 'type' for a given scapy field.
    We look at the name, the scapy class, and the actual value.
    Returns one of ["uint8", "uint16", "uint32", "int8", "int16", "int32",
                    "fixed", "bytes", "string", "crc32", "ip_checksum", "md5", ...]
    """
    lname = field_name.lower()

    # If it's obviously a string in scapy (StrField) or we see user data
    if isinstance(field_class, StrField):
        return "string"

    # If scapy tells us it's a ByteField or BitField
    if isinstance(field_class, ByteField) or isinstance(field_class, BitField):
        return "uint8"

    # ShortField or XShortField is typically 16 bits
    if isinstance(field_class, ShortField) or isinstance(field_class, XShortField):
        # You could decide "int16" if it's signed, but scapy rarely uses signed fields
        return "uint16"

    # IntField or XIntField is typically 32 bits
    if isinstance(field_class, IntField) or isinstance(field_class, XIntField):
        return "uint32"

    # If the field name suggests a checksum
    if "chksum" in lname or "checksum" in lname:
        # Example: treat 16-bit checksums as IP checksums
        # or 32-bit as CRC
        # You can do a length-based approach if you detect it's 16 bits -> "ip_checksum"
        # For simplicity, we'll just do a single approach here:
        return "ip_checksum"

    # If the field name suggests 'len' or 'length'
    if "len" in lname or "length" in lname:
        # Often 16 bits, but depends on the actual size
        # We'll guess 16 bits for demonstration
        return "uint16"

    # If it's a FieldLenField or variable-len
    if isinstance(field_class, FieldLenField):
        return "uint16"

    # If it's a list or unknown, fallback to "bytes"
    if isinstance(field_value, (list, tuple)):
        return "bytes"

    # If the value is a python string, treat it as "string"
    if isinstance(field_value, str):
        return "string"

    # If we see raw bytes
    if isinstance(field_value, (bytes, bytearray)):
        return "bytes"

    # Fallback
    return "bytes"


def find_field_offset_and_length(raw_bytes: bytes, sub_bytes: bytes, start_search: int = 0) -> tuple:
    """
    Attempt to locate 'sub_bytes' in 'raw_bytes' starting at or after 'start_search'.
    Returns (offset, length).
    If not found, returns something naive.
    This helps to find the exact offset for a field's data in the entire packet.
    """
    if not sub_bytes:
        # Zero-length field or unknown
        return (start_search, 0)

    # Try a basic substring search
    idx = raw_bytes.find(sub_bytes, start_search)
    if idx == -1:
        # fallback: not found, just guess
        return (start_search, len(sub_bytes))
    else:
        return (idx, len(sub_bytes))


def dissect_layer_fields(
    pkt: Packet,
    layer_name: str,
    unify: bool = False,
    parse_dhcp_options: bool = True
) -> dict:
    """
    Dissect the specified layer within 'pkt' and return a dict describing each field:
    {
      'field_name': {
        'offset': ...,
        'length': ...,
        'type': ...,
      },
      ...
    }

    If unify=True, we might return partial data so it can be merged with other packets.

    """
    layer = pkt.getlayer(layer_name)
    if not layer:
        return {}

    raw_pkt = bytes(pkt)
    layer_raw = bytes(layer)

    layer_offset_guess = raw_pkt.find(layer_raw)
    if layer_offset_guess < 0:
        layer_offset_guess = 0  # fallback

    field_map = {}  # field_name -> { offset, length, type }
    scapy_fields = layer.fields_desc
    current_search_ptr = layer_offset_guess

    for fdesc in scapy_fields:
        field_name = fdesc.name
        field_value = layer.getfieldval(field_name)
        if field_value is None:
            continue

        ftype = guess_fuzzer_type(field_name, fdesc, field_value)

        # Convert the value to raw bytes if possible, for offset detection
        if isinstance(field_value, int):
            # based on ftype, figure out how many bytes to represent
            if "8" in ftype:
                blen = 1
            elif "16" in ftype:
                blen = 2
            elif "32" in ftype:
                blen = 4
            else:
                blen = 1  # fallback
            sub_bytes = field_value.to_bytes(blen, "big", signed=("int" in ftype))
        elif isinstance(field_value, (bytes, bytearray)):
            sub_bytes = field_value
        elif isinstance(field_value, str):
            sub_bytes = field_value.encode('utf-8', errors='ignore')
        else:
            # fallback: skip offset detection
            sub_bytes = b""

        offset, length = find_field_offset_and_length(raw_pkt, sub_bytes, current_search_ptr)

        # Move the pointer forward so subsequent finds happen after this field
        new_search_ptr = offset + length
        if new_search_ptr > current_search_ptr:
            current_search_ptr = new_search_ptr

        field_map[field_name] = {
            "offset": offset,
            "length": length,
            "type": ftype,
        }

    # DEMO: If it's DHCP, parse the "options" sub-field as repeated fields
    if parse_dhcp_options and layer_name.upper() == "DHCP":
        options_field_name = "options"  # scapy uses 'options'
        opts_data = layer.getfieldval(options_field_name)
        if opts_data and isinstance(opts_data, list):
            for i, (opt_type, opt_val) in enumerate(opts_data):
                # Convert to bytes
                if isinstance(opt_val, int):
                    opt_bytes = opt_val.to_bytes(1, "big")
                elif isinstance(opt_val, (bytes, bytearray)):
                    opt_bytes = opt_val
                elif isinstance(opt_val, str):
                    opt_bytes = opt_val.encode('utf-8', errors='ignore')
                elif isinstance(opt_val, list):
                    # e.g. a list of bytes or ints
                    opt_bytes = b''.join(
                        v.to_bytes(1, 'big') if isinstance(v, int) else bytes(v) for v in opt_val
                    )
                else:
                    opt_bytes = b""

                # stupid search
                offset_opt, length_opt = find_field_offset_and_length(raw_pkt, opt_bytes, current_search_ptr)

                # name it something like "dhcp_option_<type>_<i>"
                f_name = f"option_{opt_type}_{i}"
                field_map[f_name] = {
                    "offset": offset_opt,
                    "length": length_opt,
                    "type": "bytes",  # or guess from content
                }
                current_search_ptr = max(current_search_ptr, offset_opt + length_opt)

    return field_map


def merge_field_maps(map_list):
    """
    Merge multiple field maps (from multiple packets) into a single 'superset' spec.
    We'll unify them by field name. If offsets differ across packets, we might store the
    minimum or 0. If lengths differ, pick the max. This is a simplistic approach.
    """
    merged = {}
    for fm in map_list:
        for field_name, fd in fm.items():
            if field_name not in merged:
                merged[field_name] = fd.copy()
            else:
                # unify
                existing = merged[field_name]
                if fd["offset"] != existing["offset"]:
                    existing["offset"] = min(existing["offset"], fd["offset"])
                if fd["length"] > existing["length"]:
                    existing["length"] = fd["length"]
                if fd["type"] != existing["type"]:
                    existing["type"] = "bytes"
    return merged


def build_json_spec(format_name: str, field_map: dict) -> dict:
    """
    Convert the dictionary of field info into the final JSON structure with "fields" array.
    Sort by offset ascending so the final JSON is more readable in offset order.
    """
    # Sort fields by offset
    sorted_fields = sorted(field_map.items(), key=lambda x: x[1]["offset"])
    fields_array = []
    for fname, finfo in sorted_fields:
        fields_array.append({
            "name": fname,
            "offset": finfo["offset"],
            "length": finfo["length"],
            "type": finfo["type"]
        })

    return {
        "format_name": format_name,
        "fields": fields_array
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate a fuzz format JSON from a PCAP for a given scapy protocol layer."
    )
    parser.add_argument("pcap", help="PCAP file to read.")
    parser.add_argument("layer", help="Protocol layer name in Scapy (e.g. DHCP, DNS, FTP, HTTP).")
    parser.add_argument(
        "--mode",
        choices=["single", "multiple", "unified"],
        default="single",
        help="""
        single   = parse the first packet found with that layer, generate one JSON
        multiple = parse ALL packets with that layer, generate one JSON per packet
        unified  = parse ALL packets with that layer, unify fields into a single 'superset' JSON
        """,
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to put generated JSON file(s)."
    )
    parser.add_argument(
        "--out",
        default="format_spec.json",
        help="Output JSON file name (used in 'single' or 'unified' modes)."
    )
    parser.add_argument(
        "--parse-dhcp-options",
        action="store_true",
        help="If set and layer=DHCP, try to parse each DHCP option as a separate field."
    )
    args = parser.parse_args()

    if not os.path.exists(args.pcap):
        logger.error(f"PCAP file not found: {args.pcap}")
        return

    packets = rdpcap(args.pcap)
    matched_packets = []

    for p in packets:
        if p.haslayer(args.layer):
            matched_packets.append(p)

    if not matched_packets:
        logger.error(f"No packets found with layer '{args.layer}' in {args.pcap}")
        return

    os.makedirs(args.output_dir, exist_ok=True)

    if args.mode == "single":
        # Just take the first matching packet
        chosen = matched_packets[0]
        field_map = dissect_layer_fields(
            chosen, args.layer,
            unify=False,
            parse_dhcp_options=args.parse_dhcp_options
        )
        spec = build_json_spec(args.layer.lower(), field_map)
        out_path = os.path.join(args.output_dir, args.out)
        with open(out_path, "w") as f:
            json.dump(spec, f, indent=2)
        logger.info(f"Wrote single format spec to {out_path}")

    elif args.mode == "multiple":
        # Generate one JSON per matched packet
        for i, pkt in enumerate(matched_packets):
            field_map = dissect_layer_fields(
                pkt, args.layer,
                unify=False,
                parse_dhcp_options=args.parse_dhcp_options
            )
            spec = build_json_spec(args.layer.lower(), field_map)
            out_path = os.path.join(args.output_dir, f"{args.layer.lower()}_{i:03d}.json")
            with open(out_path, "w") as f:
                json.dump(spec, f, indent=2)
            logger.info(f"Packet {i} spec => {out_path}")

    else:  # unified
        field_maps = []
        for i, pkt in enumerate(matched_packets):
            fm = dissect_layer_fields(
                pkt, args.layer,
                unify=True,
                parse_dhcp_options=args.parse_dhcp_options
            )
            field_maps.append(fm)
        merged = merge_field_maps(field_maps)
        spec = build_json_spec(args.layer.lower(), merged)
        out_path = os.path.join(args.output_dir, args.out)
        with open(out_path, "w") as f:
            json.dump(spec, f, indent=2)
        logger.info(f"Wrote unified format spec to {out_path}")


if __name__ == "__main__":
    main()

