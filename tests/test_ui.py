from handmusic.ui.desktop import list_midi_output_ports


def test_midi_port_discovery_is_a_safe_list() -> None:
    ports = list_midi_output_ports()

    assert isinstance(ports, list)
    assert all(isinstance(port, str) for port in ports)
