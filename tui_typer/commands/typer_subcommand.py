from typing import Any

from loguru import logger
import pandas as pd
import typer

__app_name__ = "serialize"


reports = [
    {
        "title": "Sample Report",
        "columns": ["Name", "Age", "City"],
        "rows": [
            {"Name": "Alice", "Age": 30, "City": "New York"},
            {"Name": "Bob", "Age": 25, "City": "Los Angeles"},
            {"Name": "Charlie", "Age": 35, "City": "Chicago"},
        ],
    }
]


class Serializer:
    """A general serializer for dict type data structures"""

    @staticmethod
    def serialize_to_excel(reports: list, file_name: str):
        """
        Serialize a list of reports to an Excel file. Each report is a dictionary on the following format
        {'title': str,
        'columns': List[str],
        'rows': List[Dict[str, Any]]}

        Args:
            report: list of reports to serialize
            file_name: the output file name
        """
        with pd.ExcelWriter(file_name) as writer:
            for report in reports:
                df = pd.DataFrame(report["rows"], columns=report["columns"])
                sheet_name = report.get("title", "Sheet1")
                df.to_excel(writer, sheet_name=sheet_name, index=False)


serialize = typer.Typer(help="Serialisation of a report to Excel.")


@serialize.command()
def excel(
    file_name: str = typer.Option("report.xlsx", "--file-name", "-f", help="The excel file name"),
):
    """Serialize the reports to Excel"""

    Serializer.serialize_to_excel(reports, file_name)
    logger.info(f"Serialized report to Excel file: {file_name}")


def cli_plugin() -> tuple[str, Any]:
    """
    ClI plugin

    Returns the typer command object
    """
    subcommand = typer.main.get_command(serialize)
    return __app_name__, subcommand
