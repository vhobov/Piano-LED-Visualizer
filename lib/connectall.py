#!/usr/bin/python3
import subprocess
import sys
import os
import re
from xml.etree import ElementTree as ET


def connectall(usersettings=None):
    """
    Connect input and secondary input ports if they are both set and not 'default'.
    If usersettings is provided, use it. Otherwise, read settings from config file.
    """
    # Get settings
    if usersettings is not None:
        input_port = usersettings.get_setting_value("input_port")
        secondary_input_port = usersettings.get_setting_value("secondary_input_port")
    else:
        # Read settings from config file directly
        # Try multiple possible locations for the settings file
        settings_paths = [
            "config/settings.xml",  # When called from app directory
            "/home/Piano-LED-Visualizer/config/settings.xml",  # When called from system
            "/opt/Piano-LED-Visualizer/config/settings.xml",  # Alternative system path
        ]
        
        settings_found = False
        for settings_path in settings_paths:
            try:
                if os.path.exists(settings_path):
                    tree = ET.parse(settings_path)
                    root = tree.getroot()
                    input_port = root.find("./input_port").text if root.find("./input_port") is not None else "default"
                    secondary_input_port = root.find("./secondary_input_port").text if root.find("./secondary_input_port") is not None else "default"
                    settings_found = True
                    print(f"Using settings from: {settings_path}")
                    break
            except:
                continue
        
        if not settings_found:
            print("ERROR: Could not read settings file from any location, using defaults")
            input_port = "default"
            secondary_input_port = "default"
    
    # Check if both ports are set and not default
    if input_port == "default" or secondary_input_port == "default":
        print("INFO: Input port or secondary input port not set, skipping connection")
        return
    
    if input_port == secondary_input_port:
        print("INFO: Input and secondary input ports are the same, skipping connection")
        return
    
    # Get available ports
    ports = subprocess.check_output(["aconnect", "-i", "-l"], text=True)
    port_list = []
    client = "0"
    for line in str(ports).splitlines():
        if line.startswith("client "):
            client = line[7:].split(":", 2)[0]
            if client == "0" or "Through" in line or "RtMidi" in line:
                client = "0"
        else:
            if client == "0" or line.startswith('\t'):
                continue
            port = line.split()[0]
            port_list.append(client + ":" + port)
    
    # Find the actual port IDs for the configured ports
    input_port_id = None
    secondary_input_port_id = None
    
    # Extract the port ID from the configured port names
    # Format: "client_name:port_name client_id:port_id"
    try:
        input_port_id = input_port.split()[-1]  # Get the last part (client_id:port_id)
        secondary_input_port_id = secondary_input_port.split()[-1]  # Get the last part (client_id:port_id)
    except:
        print("ERROR: Failed to parse configured port names")
        return
    
    # Verify the ports exist in the available port list
    if input_port_id not in port_list:
        print(f"ERROR: Input port ID '{input_port_id}' not found in available ports")
        input_port_id = None
    
    if secondary_input_port_id not in port_list:
        print(f"ERROR: Secondary input port ID '{secondary_input_port_id}' not found in available ports")
        secondary_input_port_id = None
    
    # Connect the ports if both are found
    if input_port_id and secondary_input_port_id:
        # Check if the desired connection already exists before doing anything
        aconnect_output = subprocess.check_output(["aconnect", "-l"], text=True)
        connection_exists = _check_connection_exists(aconnect_output, input_port_id, secondary_input_port_id)
        
        if connection_exists:
            print(f"SUCCESS: Connection between {input_port} and {secondary_input_port} already exists, skipping")
        else:
            print(f"INFO: Attempting to connect {input_port} ({input_port_id}) to {secondary_input_port} ({secondary_input_port_id})")
            # Two-way connection: input -> secondary and secondary -> input
            result1 = subprocess.run(f"aconnect {input_port_id} {secondary_input_port_id}", shell=True, capture_output=True, text=True)
            result2 = subprocess.run(f"aconnect {secondary_input_port_id} {input_port_id}", shell=True, capture_output=True, text=True)
            
            # Check results and provide detailed feedback
            success1 = result1.returncode == 0 or "Connection is already subscribed" in result1.stderr
            success2 = result2.returncode == 0 or "Connection is already subscribed" in result2.stderr
            
            if success1 and success2:
                if result1.returncode == 0 and result2.returncode == 0:
                    print("SUCCESS: Connection established successfully")
                else:
                    print("SUCCESS: Connection already exists (both directions)")
            else:
                # Report specific failures
                if not success1:
                    print(f"ERROR: Failed to connect {input_port_id} -> {secondary_input_port_id}: {result1.stderr.strip()}")
                if not success2:
                    print(f"ERROR: Failed to connect {secondary_input_port_id} -> {input_port_id}: {result2.stderr.strip()}")
                print("WARNING: Some connections may have failed")
    else:
        print(f"ERROR: Could not find ports: input_port='{input_port}', secondary_input_port='{secondary_input_port}'")
        if not input_port_id:
            print(f"ERROR: Input port '{input_port}' not found")
        if not secondary_input_port_id:
            print(f"ERROR: Secondary input port '{secondary_input_port}' not found")


def is_connected(usersettings) -> bool:
    """Check whether the currently configured input_port and secondary_input_port
    are presently two-way connected over ALSA. Used by the web UI to prefill the
    'auto-connect' checkbox when saving the current port selection as a setup."""
    input_port = usersettings.get_setting_value("input_port")
    secondary_input_port = usersettings.get_setting_value("secondary_input_port")

    if not input_port or not secondary_input_port:
        return False
    if input_port == "default" or secondary_input_port == "default":
        return False
    if input_port == secondary_input_port:
        return False

    try:
        input_port_id = input_port.split()[-1]
        secondary_input_port_id = secondary_input_port.split()[-1]
        aconnect_output = subprocess.check_output(["aconnect", "-l"], text=True)
        return _check_connection_exists(aconnect_output, input_port_id, secondary_input_port_id)
    except Exception:
        return False


def _check_connection_exists(aconnect_output, input_port_id, secondary_input_port_id):
    """Check if the desired two-way connection already exists"""
    try:
        lines = aconnect_output.splitlines()
        input_to_secondary = False
        secondary_to_input = False
        
        for line in lines:
            # Look for "Connecting To:" lines that contain both port IDs
            if "Connecting To:" in line:
                if input_port_id in line and secondary_input_port_id in line:
                    # This line shows a connection between our two ports
                    input_to_secondary = True
                    secondary_to_input = True
                    break
            # Also check for "Connected From:" lines for completeness
            elif "Connected From:" in line:
                if input_port_id in line and secondary_input_port_id in line:
                    input_to_secondary = True
                    secondary_to_input = True
                    break
        
        return input_to_secondary and secondary_to_input
        
    except Exception as e:
        print(f"ERROR: Failed to check connection existence: {e}")
        return False


def _is_internal_client(client_id, client_name):
    """True for ALSA clients that aren't real user-facing MIDI devices the
    Setups feature should try to manage: the kernel Timer/Announce client,
    the Midi Through virtual port, the per-process RtMidiIn/RtMidiOut clients
    mido itself creates whenever it opens a port, and rtpmidid - which
    auto-exports every local ALSA MIDI port over the network on its own and
    reacts to losing that subscription by immediately re-establishing it, so
    disconnecting/reconnecting it from here just fights the daemon instead of
    reflecting anything the user actually drew."""
    return (client_id == "0" or "Through" in client_name or "RtMidi" in client_name
            or client_name == "rtpmidid")


def _parse_client_ports_and_links(aconnect_output):
    """Parse `aconnect -l` output into (id_to_name, links), excluding internal
    ALSA clients entirely (see _is_internal_client) so neither their ports nor
    any connection touching them - as either endpoint - show up. Two passes:
    the first finds every internal client id regardless of where it's
    declared in the dump, so a link to a client declared later in the output
    is still filtered correctly. id_to_name maps 'client:port' -> (client_name,
    port_name). links is a list of (source_id, destination_id) 'client:port'
    tuples for every live 'Connecting To:' edge between two non-internal
    ports."""
    lines = aconnect_output.splitlines()

    internal_client_ids = set()
    for line in lines:
        client_match = re.match(r"client (\d+):\s+'([^']+)'", line.strip())
        if client_match and _is_internal_client(client_match.group(1), client_match.group(2)):
            internal_client_ids.add(client_match.group(1))

    id_to_name = {}
    links = []
    current_client = current_client_name = current_port = None
    skip_client = False

    for line in lines:
        stripped = line.strip()

        client_match = re.match(r"client (\d+):\s+'([^']+)'", stripped)
        if client_match:
            current_client, current_client_name = client_match.group(1), client_match.group(2)
            current_port = None
            skip_client = current_client in internal_client_ids
            continue

        if skip_client:
            continue

        if current_client and line.startswith('    ') and not line.startswith('\t'):
            port_match = re.match(r"(\d+)\s+'([^']+)'", stripped)
            if port_match:
                current_port = port_match.group(1)
                id_to_name[f"{current_client}:{current_port}"] = (current_client_name, port_match.group(2))
                continue

        if current_client and current_port and '\t' in line and "Connecting To:" in stripped:
            source_id = f"{current_client}:{current_port}"
            for dest_client, dest_port in re.findall(r"(\d+):(\d+)", stripped):
                if dest_client in internal_client_ids:
                    continue
                links.append((source_id, f"{dest_client}:{dest_port}"))

    return id_to_name, links


def capture_custom_connections():
    """Snapshot every currently-live custom ALSA MIDI connection (excluding
    internal clients - see _is_internal_client) as a list of {source_client,
    source_port, dest_client, dest_port} dicts, keyed by descriptive
    device/port name rather than 'client:port' ID - those IDs get reshuffled
    on every reboot or USB replug, but the names stay stable."""
    try:
        output = subprocess.check_output(["aconnect", "-l"], text=True)
    except Exception:
        return []

    id_to_name, links = _parse_client_ports_and_links(output)

    connections = []
    seen = set()
    for source_id, dest_id in links:
        if source_id not in id_to_name or dest_id not in id_to_name or source_id == dest_id:
            continue
        if (source_id, dest_id) in seen:
            continue
        seen.add((source_id, dest_id))
        source_client, source_port = id_to_name[source_id]
        dest_client, dest_port = id_to_name[dest_id]
        connections.append({
            "source_client": source_client, "source_port": source_port,
            "dest_client": dest_client, "dest_port": dest_port,
        })
    return connections


def _resolve_id(id_to_name, client_name, port_name):
    """Find the current 'client:port' ID whose descriptive name matches a
    captured connection's endpoint."""
    for cp_id, (c_name, p_name) in id_to_name.items():
        if c_name == client_name and p_name == port_name:
            return cp_id
    for cp_id, (c_name, p_name) in id_to_name.items():
        if c_name == client_name:
            return cp_id
    return None


def apply_custom_connections(connections, managed_pair=None):
    """Make the live custom ALSA connections match `connections` exactly:
    disconnects any current custom connection that isn't in the list, then
    (re)creates every one that is, re-resolving each endpoint's descriptive
    name against the currently live port list since 'client:port' IDs get
    reshuffled by reboot/replug. A device that isn't plugged in right now is
    skipped, not fatal.

    managed_pair, if given, is the (input_id, secondary_id) 'client:port' pair
    connectall() itself just bridged - it's left untouched by the cleanup pass
    even if it isn't part of `connections`, so this function never undoes the
    primary input/secondary bridge."""
    try:
        output = subprocess.check_output(["aconnect", "-l"], text=True)
    except Exception as e:
        print(f"ERROR: Could not list ALSA ports to restore custom connections: {e}")
        return

    id_to_name, live_links = _parse_client_ports_and_links(output)

    protected = set()
    if managed_pair:
        protected = {tuple(managed_pair), tuple(reversed(managed_pair))}

    wanted = set()
    for conn in connections or []:
        source_id = _resolve_id(id_to_name, conn.get("source_client"), conn.get("source_port"))
        dest_id = _resolve_id(id_to_name, conn.get("dest_client"), conn.get("dest_port"))
        if not source_id or not dest_id:
            print(f"WARNING: Skipping custom connection, device not found: "
                  f"{conn.get('source_client')} -> {conn.get('dest_client')}")
            continue
        wanted.add((source_id, dest_id))

    for source_id, dest_id in live_links:
        if (source_id, dest_id) in protected or (source_id, dest_id) in wanted:
            continue
        result = subprocess.run(["aconnect", "-d", source_id, dest_id], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"WARNING: Failed to remove stale custom connection {source_id} -> {dest_id}: "
                  f"{result.stderr.strip()}")

    for source_id, dest_id in wanted:
        result = subprocess.run(["aconnect", source_id, dest_id], capture_output=True, text=True)
        if result.returncode != 0 and "already subscribed" not in result.stderr:
            print(f"WARNING: Failed to restore custom connection {source_id} -> {dest_id}: {result.stderr.strip()}")


if __name__ == '__main__':
    connectall()
