"""Synthetic installation and client fixtures, with no live API or user data."""

import json
import shutil
import tempfile
from pathlib import Path

from AutoCua.saccade.business_contract import digest
from AutoCua.saccade.business_run import BusinessRun
from AutoCua.saccade.session_context import build_platform_context

REPOSITORY = Path(__file__).resolve().parents[1]


class BusinessFixture:
    def __init__(self):
        directory = REPOSITORY / ".cache/business-tests"
        directory.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=directory)
        self.root = Path(self.temporary.name)
        self.package = self.root / "installed/AutoCua"
        self.package.mkdir(parents=True)
        for name in ("__init__.py", "saccade/__init__.py", "saccade/platform_config.py", "saccade/session_context.py",
                     "saccade/business_contract.py", "saccade/business_catalogue.py", "saccade/business_run.py",
                     "saccade/business_process.py", "saccade/business_worker.py",
                     "saccade/business_functions/__init__.py", "saccade/business_functions/platforms/__init__.py"):
            path = self.package / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPOSITORY / "AutoCua" / name, path)
        self.functions = self.package / "saccade/business_functions/platforms/dext"
        shutil.copytree(REPOSITORY / "AutoCua/saccade/business_functions/platforms/dext", self.functions,
                        ignore=shutil.ignore_patterns("__pycache__"))
        domain = self.root / "AutoCua/default_skills/web/domain_skill"
        domain.mkdir(parents=True)
        (domain / "skills.json").write_text('{"app.dext.com":"dext.md"}', encoding="utf-8")
        (domain / "dext.md").write_text("", encoding="utf-8")
        platform = self.root / "platforms/dext"
        platform.mkdir(parents=True)
        shutil.copyfile(REPOSITORY / "platforms/dext/platform.json", platform / "platform.json")
        self.data = platform / "data"
        (self.data / "synthetic-alpha").mkdir(parents=True)
        self.registration = {"schema_version": 1, "active_client": "synthetic-alpha", "clients": {
            "synthetic-alpha": {"synthetic": True, "bank_labels": ["SYNTHETIC BANK", "AMBIGUOUS", "UNKNOWN"],
                                "bank_responses": {"SYNTHETIC BANK": {"compte": "40100000"}}},
            "synthetic-other": {"synthetic": True, "bank_labels": ["OTHER BANK"], "bank_responses": {}}}}
        self.write_registration()
        self.reference = self.data / "synthetic-alpha/comptable_banque.md"
        self.reference.write_text("Entire synthetic bank reference, including final rule.\n", encoding="utf-8")
        for name in ("comptable_achats.md", "comptable_ventes.md"):
            (self.data / "synthetic-alpha" / name).write_text("Entire synthetic invoice reference.\n", encoding="utf-8")
        self.context = build_platform_context("dext", root=self.root)

    def write_registration(self):
        (self.data / "registration.json").write_text(json.dumps(self.registration), encoding="utf-8")

    def run(self, **kwargs):
        run = BusinessRun(self.context, project_root=self.root, package_root=self.package, **kwargs)
        run.refresh()
        return run

    def action(self, **changes):
        action = {"type": "call_function", "version": 1, "name": "dext.bank",
                  "arguments": {"string": "SYNTHETIC BANK", "client_id": "synthetic-alpha"}}
        action.update(changes)
        return action

    def invoice(self):
        proposal = {"type": "facture", "statut": "proposee", "motifs": [], "journal": "ACH",
                    "piece": {"tiers": "Synthetic Party", "identifiant_tiers": None, "reference": "SYNTHETIC-001",
                              "date": "2026-01-01", "description": "Synthetic fixture", "devise": "EUR",
                              "total_centimes": 12000, "tva_centimes": 2000},
                    "ecriture": [{"compte": "601000", "role": "base", "debit_centimes": 10000, "credit_centimes": 0},
                                 {"compte": "445660", "role": "tva", "debit_centimes": 2000, "credit_centimes": 0},
                                 {"compte": "401000", "role": "tiers", "debit_centimes": 0, "credit_centimes": 12000}]}
        path = self.data / "synthetic-alpha/synthetic.pdf"
        path.write_bytes(b"%PDF-1.4\n% Synthetic offline fixture, no customer document.\n%%EOF")
        critical = {"type": "facture", "journal": "ACH", "accounts": [row["compte"] for row in proposal["ecriture"]],
                    "piece": {k: proposal["piece"][k] for k in ("reference", "date", "tiers", "devise", "total_centimes", "tva_centimes")}}
        return {"fixture-one": {"client_id": "synthetic-alpha", "sens": "achat",
                                "relative_path": "synthetic-alpha/synthetic.pdf", "sha256": digest(path.read_bytes()),
                                "expected": proposal, "critical": critical}}

    def close(self):
        self.temporary.cleanup()
