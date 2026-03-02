from __future__ import annotations

import json
from pathlib import Path

from .models import OperationSummary, OperationTransaction, TransactionAction


class TransactionService:
    def save_transaction(self, transaction: OperationTransaction) -> Path:
        tx_root = transaction.target_root / ".filegrouper" / "transactions"
        tx_root.mkdir(parents=True, exist_ok=True)
        filename = f"{transaction.created_at_utc.strftime('%Y%m%d_%H%M%S')}_{transaction.transaction_id}.json"
        destination = tx_root / filename
        with destination.open("w", encoding="utf-8") as stream:
            json.dump(transaction.to_dict(), stream, ensure_ascii=True, indent=2)
        return destination

    def find_latest_transaction_file(self, target_root: Path) -> Path | None:
        tx_root = target_root / ".filegrouper" / "transactions"
        if not tx_root.is_dir():
            return None

        files = sorted(tx_root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        return files[0] if files else None

    def load(self, transaction_file: Path) -> OperationTransaction:
        with transaction_file.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
        return OperationTransaction.from_dict(payload)

    def undo_last_transaction(self, target_root: Path, log=None) -> OperationSummary:
        latest = self.find_latest_transaction_file(target_root)
        if latest is None:
            raise RuntimeError("No transaction file found for undo.")
        return self.undo_transaction(latest, log=log)

    def undo_transaction(self, transaction_file: Path, log=None) -> OperationSummary:
        transaction = self.load(transaction_file)
        summary = OperationSummary()

        for entry in reversed(transaction.entries):
            try:
                if entry.action is TransactionAction.COPIED:
                    if entry.destination_path and entry.destination_path.exists():
                        entry.destination_path.unlink(missing_ok=True)
                        summary.files_copied += 1
                elif entry.action is TransactionAction.MOVED:
                    if entry.destination_path and entry.destination_path.exists():
                        entry.source_path.parent.mkdir(parents=True, exist_ok=True)
                        entry.destination_path.rename(entry.source_path)
                        summary.files_moved += 1
                elif entry.action is TransactionAction.QUARANTINED_DUPLICATE:
                    if entry.destination_path and entry.destination_path.exists():
                        entry.source_path.parent.mkdir(parents=True, exist_ok=True)
                        entry.destination_path.rename(entry.source_path)
                        summary.duplicates_quarantined += 1
                elif entry.action is TransactionAction.DELETED_DUPLICATE:
                    summary.duplicates_deleted += 1
                    if log:
                        log(f"Skipped deleted duplicate restore: {entry.source_path}")
            except Exception as exc:  # noqa: BLE001
                summary.errors.append(f"Undo failed for '{entry.source_path}': {exc}")

        return summary
