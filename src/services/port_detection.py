"""Port detection for services."""
import subprocess
import re
from dataclasses import dataclass
from typing import List


@dataclass
class PortInfo:
    """Port information."""
    port: int
    pid: int


class PortDetection:
    """Service for detecting listening ports."""

    # Web service port ranges
    WEB_PORTS = {80, 443}
    WEB_PORT_RANGES = [
        (3000, 3999),
        (4000, 4999),
        (5000, 5999),
        (8000, 8999),
        (9000, 9999),
    ]

    def get_listening_ports(self) -> List[PortInfo]:
        """Get all listening TCP ports with their PIDs.

        Returns:
            List of PortInfo objects
        """
        result = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True,
            text=True,
            check=True
        )
        return self._parse_ss_output(result.stdout)

    def _parse_ss_output(self, output: str) -> List[PortInfo]:
        """Parse ss -tlnp output.

        Args:
            output: Raw output from ss command

        Returns:
            List of PortInfo objects
        """
        ports = []
        for line in output.strip().split('\n'):
            # Match pattern like: tcp   LISTEN 0   128   0.0.0.0:80   0.0.0.0:*   users:(("nginx",pid=1234,fd=6))
            port_match = re.search(r':(\d+)\s+', line)
            pid_match = re.search(r'pid=(\d+)', line)

            if port_match and pid_match:
                port = int(port_match.group(1))
                pid = int(pid_match.group(1))
                ports.append(PortInfo(port=port, pid=pid))

        return ports

    def is_web_port(self, port: int) -> bool:
        """Check if a port is typically used for web services.

        Args:
            port: Port number to check

        Returns:
            True if port is in web service range
        """
        if port in self.WEB_PORTS:
            return True

        for start, end in self.WEB_PORT_RANGES:
            if start <= port <= end:
                return True

        return False

    def get_ports_for_pid(self, ports: List[PortInfo], pid: int) -> List[PortInfo]:
        """Filter ports for a specific PID.

        Args:
            ports: List of all port info
            pid: Process ID to filter by

        Returns:
            List of PortInfo for the specified PID
        """
        return [p for p in ports if p.pid == pid]
