"""Systemd service discovery."""
import subprocess
import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SystemdService:
    """Systemd service information."""
    name: str
    state: str
    description: str = ""


class SystemdDiscovery:
    """Service for discovering systemd services."""

    def list_services(self) -> List[SystemdService]:
        """List all systemd services.

        Returns:
            List of SystemdService objects
        """
        result = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--all", "--no-pager", "--plain"],
            capture_output=True,
            text=True,
            check=True
        )
        return self._parse_systemctl_list(result.stdout)

    def _parse_systemctl_list(self, output: str) -> List[SystemdService]:
        """Parse systemctl list-units output.

        Args:
            output: Raw output from systemctl list-units

        Returns:
            List of SystemdService objects
        """
        services = []
        for line in output.strip().split('\n'):
            if not line.strip():
                continue

            # Parse format: "  service.service    loaded active running   Description"
            parts = line.split()
            if len(parts) >= 4:
                name = parts[0]

                # Skip header line and non-service entries
                if name == "UNIT" or not name.endswith(".service"):
                    continue

                state = parts[2]  # active/inactive/failed
                description = ' '.join(parts[4:]) if len(parts) > 4 else ""
                services.append(SystemdService(name=name, state=state, description=description))

        return services

    def get_service_pid(self, service_name: str) -> Optional[int]:
        """Get the main PID for a service.

        Args:
            service_name: Name of the systemd service

        Returns:
            PID as integer, or None if not running
        """
        result = subprocess.run(
            ["systemctl", "show", service_name, "--property=MainPID"],
            capture_output=True,
            text=True,
            check=True
        )

        match = re.search(r'MainPID=(\d+)', result.stdout)
        if match:
            pid = int(match.group(1))
            return pid if pid > 0 else None

        return None
