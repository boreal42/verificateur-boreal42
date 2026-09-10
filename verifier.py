#!/usr/bin/env python3
"""Vérificateur documentaire du pack Boréal42.

Fichier GÉNÉRÉ en amont, copié ici par l'installeur. Ne pas modifier à la main :
`.claude/chemins-geles` le protège et la prochaine synchronisation écraserait la
retouche. Ce qui varie se règle dans `.claude/verifier.toml`.

Version 1 · 2026-09-10 · Boréal42

Applique dix règles documentaires, et dix seulement. Le lint, le typage et les
tests restent la responsabilité du projet : ce script les *appelle* par
délégation, via les cibles déclarées dans `.claude/verifier.toml`. Sans cette
frontière, un script partagé et les cibles d'un projet finissent par se
contredire.

    1. ligne de statut présente, en ligne 3, date au jour           
    2. état dans la liste fermée                                    
    3. quatre champs fixes sur la ligne de statut                   
    4. aucun en-tête YAML `autorite:`                               
    5. CLAUDE.md sous le seuil de lignes                            
    6. chemins des exemples canoniques existants                    
    7. liens relatifs résolus
    8. aucun fichier sensible suivi par git
       — les gabarits .env.example et consorts sont exclus : ils sont faits
         pour être versionnés et ne portent jamais de valeur
    9. aucune technologie citée par CLAUDE.md et absente du dépôt
   10. aucun marqueur « À REMPLIR » restant

Bibliothèque standard seule : la CI ne résout aucune dépendance et n'a besoin
d'aucun jeton.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

VERSION = "1"

# --- Réglages par défaut, surchargés par .claude/verifier.toml ----------------

ETATS = [
    "brouillon", "en revue", "approuvé", "en exécution", "livré",
    "accepté", "réalisé", "actif", "figé", "historique",
]
# `remplacé par X` est reconnu à part : il porte une cible.
CHAMPS = ["Statut", "Version", "Mise à jour", "Source"]
SEUIL_CLAUDE_MD = 200
RACINE_DOCS = "docs"

SENSIBLE = re.compile(
    r"(^|/)(\.env(\.(?!example$|sample$|template$|dist$)[^/]*)?"
    r"|[^/]*\.pem|[^/]*\.key|id_rsa[^/]*"
    r"|\.credentials\.json|settings\.local\.json|\.mcp\.json)$"
)

# Technologies détectables : nom cité dans le CLAUDE.md -> preuve de présence.
# Une entrée absente du dépôt et citée dans la constitution est une sur-déclaration.
TECHNOS = {
    "postgresql": ["docker-compose*.yml", "**/alembic.ini", "**/*.sql", "compose*.yml"],
    "postgis": ["docker-compose*.yml", "compose*.yml"],
    "alembic": ["**/alembic.ini", "**/migrations/env.py", "**/alembic/env.py"],
    "sqlalchemy": ["**/requirements*.txt", "**/pyproject.toml"],
    "sqlite": ["**/*.db", "**/requirements*.txt", "**/pyproject.toml", "**/*.py"],
    "redis": ["docker-compose*.yml", "compose*.yml"],
    "angular": ["**/angular.json"],
    "react": ["**/package.json"],
    "vite": ["**/vite.config.*"],
    "fastapi": ["**/requirements*.txt", "**/pyproject.toml"],
    "django": ["**/manage.py"],
    "weaviate": ["docker-compose*.yml", "compose*.yml", "**/requirements*.txt"],
    "minio": ["docker-compose*.yml", "compose*.yml"],
}


class Verificateur:
    def __init__(self, racine: Path):
        self.racine = racine
        self.erreurs: list[str] = []
        self.avertissements: list[str] = []
        self.conf = self._charger_conf()
        self.etats = self.conf.get("etats", ETATS)
        self.seuil = self.conf.get("seuil_claude_md", SEUIL_CLAUDE_MD)
        self.docs = racine / self.conf.get("racine_docs", RACINE_DOCS)

    def _charger_conf(self) -> dict:
        chemin = self.racine / ".claude" / "verifier.toml"
        if not chemin.is_file():
            return {}
        try:
            return tomllib.loads(chemin.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001 — un TOML cassé doit être dit, pas masqué
            self.erreurs.append(f".claude/verifier.toml illisible : {e}")
            return {}

    def _rel(self, p: Path) -> str:
        try:
            return str(p.relative_to(self.racine))
        except ValueError:
            return str(p)

    # --- 1 à 4 : la ligne de statut -----------------------------------------

    def regles_statut(self) -> None:
        fichiers = sorted(self.docs.rglob("*.md")) if self.docs.is_dir() else []
        for p in fichiers:
            lignes = p.read_text(encoding="utf-8", errors="ignore").splitlines()
            tete = lignes[:12]
            rel = self._rel(p)

            # 4. aucun en-tête YAML
            if any(re.match(r"^autorite\s*:", l) for l in tete):
                self.erreurs.append(
                    f"{rel} : en-tête YAML « autorite: ». Ce dépôt utilise la ligne "
                    f"de statut, une seule convention."
                )

            statut = next((l for l in tete if re.match(r"^\*\*Statut\*\*\s*:", l)), None)
            if statut is None:
                self.erreurs.append(
                    f"{rel} : pas de ligne « **Statut** : » dans les 12 premières lignes."
                )
                continue

            # 1. en ligne 3
            if len(lignes) >= 3 and lignes[2] != statut:
                self.erreurs.append(
                    f"{rel} : la ligne de statut est en ligne {lignes.index(statut) + 1}, "
                    f"attendue en ligne 3, juste sous le titre."
                )

            # 2. état dans la liste fermée
            m = re.match(r"^\*\*Statut\*\*\s*:\s*([^·\n]+)", statut)
            valeur = m.group(1).strip() if m else ""
            base = re.sub(r"\s*\(.*?\)\s*", " ", valeur).strip()
            if not (base.startswith("remplacé par") or base in self.etats):
                self.erreurs.append(
                    f"{rel} : état « {base} » hors de la liste admise. "
                    f"Admis : {', '.join(self.etats)}, remplacé par X."
                )

            # 3. quatre champs fixes, et la date au jour
            manquants = [c for c in CHAMPS if f"**{c}**" not in statut]
            if manquants:
                self.erreurs.append(
                    f"{rel} : champs manquants sur la ligne de statut : "
                    f"{', '.join(manquants)}."
                )
            # La date n'est contrôlée que si la ligne est réputée finie : un
            # marqueur d'incomplétude est déjà signalé par la règle 10, inutile
            # de le redire sous un autre angle.
            marque = self.conf.get("marqueur_incomplet", "À REMPLIR")
            maj = re.search(r"\*\*Mise à jour\*\*\s*:\s*(\S+)", statut)
            if maj and marque not in statut and not re.match(r"^\d{4}-\d{2}-\d{2}$", maj.group(1)):
                self.erreurs.append(
                    f"{rel} : date « {maj.group(1)} » — attendue au jour, forme AAAA-MM-JJ."
                )
        print(f"== statut : {len(fichiers)} documents sous {self._rel(self.docs)}")

    # --- 5 : taille de la constitution ---------------------------------------

    def regle_taille(self) -> None:
        p = self.racine / "CLAUDE.md"
        if not p.is_file():
            self.erreurs.append("CLAUDE.md absent à la racine.")
            return
        n = len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
        if n > self.seuil:
            self.erreurs.append(
                f"CLAUDE.md : {n} lignes, seuil {self.seuil}. Ce qui déborde va "
                f"dans docs/ s'il s'agit d'un journal, dans .claude/rules/ s'il ne "
                f"concerne qu'une zone."
            )
        print(f"== constitution : CLAUDE.md {n} lignes, seuil {self.seuil}")

    # --- 6 et 7 : exemples canoniques et liens -------------------------------

    def regles_liens(self) -> None:
        fence = re.compile(r"```.*?```", re.S)
        en_ligne = re.compile(r"`[^`\n]*`")
        lien = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
        cibles = list(self.docs.rglob("*.md")) if self.docs.is_dir() else []
        cibles += [self.racine / "CLAUDE.md", self.racine / "README.md"]
        n = 0
        for p in cibles:
            if not p.is_file():
                continue
            brut = p.read_text(encoding="utf-8", errors="ignore")
            texte = en_ligne.sub("", fence.sub("", brut))
            for cible in lien.findall(texte):
                if cible.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                chemin = cible.split("#", 1)[0]
                if not chemin:
                    continue
                n += 1
                c = (Path(chemin).expanduser() if chemin.startswith(("/", "~"))
                     else p.parent / chemin)
                if not c.exists():
                    self.erreurs.append(f"{self._rel(p)} → {cible} : introuvable.")
        print(f"== liens : {n} liens relatifs résolus")

        # 6. exemples canoniques : les chemins cités sous « Golden examples »
        cm = self.racine / "CLAUDE.md"
        if not cm.is_file():
            return
        lignes = cm.read_text(encoding="utf-8", errors="ignore").splitlines()
        dedans, exemples = False, 0
        for l in lignes:
            if re.match(r"^##+\s", l):
                dedans = bool(re.search(r"golden example|exemples? canonique", l, re.I))
                continue
            if not dedans:
                continue
            for chemin in re.findall(r"`([^`\n]+)`", l):
                if "/" not in chemin or chemin.startswith(("http", "make ", "$")):
                    continue
                exemples += 1
                if not (self.racine / chemin.split(":")[0]).exists():
                    self.erreurs.append(
                        f"CLAUDE.md : exemple canonique « {chemin} » n'existe plus. "
                        f"Un exemple mort est pire que pas d'exemple."
                    )
        print(f"== exemples canoniques : {exemples} chemins cités")

    # --- 10 : l'incomplétude doit être bruyante ------------------------------
    # Le gabarit pose des fichiers complets et exécutables, jamais des
    # placeholders qui dorment. Ce qui reste à écrire porte un marqueur, et le
    # marqueur fait échouer : c'est ce qui empêche de répéter les soixante-neuf
    # placeholders jamais remplis du gabarit de juin 2026.

    def regle_a_remplir(self) -> None:
        marque = self.conf.get("marqueur_incomplet", "À REMPLIR")
        cibles = [self.racine / "CLAUDE.md"]
        if self.docs.is_dir():
            cibles += sorted(self.docs.rglob("*.md"))
        total = 0
        for p in cibles:
            if not p.is_file():
                continue
            n = sum(1 for l in p.read_text(encoding="utf-8", errors="ignore").splitlines()
                    if marque in l)
            if n:
                total += n
                self.erreurs.append(
                    f"{self._rel(p)} : {n} marqueur(s) « {marque} » restant(s). "
                    f"L'installation n'est terminée que lorsqu'il n'en reste aucun."
                )
        print(f"== complétude : {total} marqueur(s) « {marque} »")

    # --- 8 : secrets suivis ---------------------------------------------------

    def regle_secrets(self) -> list[str]:
        r = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, cwd=self.racine,
        )
        suivis = [s for s in r.stdout.split("\n") if s]
        fuites = [s for s in suivis if SENSIBLE.search(s)]
        for s in fuites:
            self.erreurs.append(f"{s} : fichier sensible suivi par git.")
        print(f"== secrets : {len(suivis)} fichiers suivis, {len(fuites)} sensible(s)")
        return suivis

    # --- 9 : la constitution ne raconte que ce qui existe --------------------

    def regle_coherence_pile(self) -> None:
        cm = self.racine / "CLAUDE.md"
        if not cm.is_file():
            return
        texte = cm.read_text(encoding="utf-8", errors="ignore").lower()
        declarees = self.conf.get("technos_declarees", [])
        ignorees = {t.lower() for t in self.conf.get("technos_ignorees", [])}
        verifiees = 0
        for nom, motifs in TECHNOS.items():
            if nom in ignorees or not re.search(rf"\b{re.escape(nom)}\b", texte):
                continue
            verifiees += 1
            if nom in {d.lower() for d in declarees}:
                continue
            trouve = any(
                any(nom in f.read_text(encoding="utf-8", errors="ignore").lower()
                    for f in self.racine.glob(motif) if f.is_file())
                or any(self.racine.glob(motif.replace("**/", "*/")))
                for motif in motifs
            )
            if not trouve:
                self.erreurs.append(
                    f"CLAUDE.md cite « {nom} », introuvable dans le dépôt. "
                    f"Corriger la constitution, ou déclarer la techno dans "
                    f"technos_declarees de .claude/verifier.toml si la détection se trompe."
                )
        print(f"== cohérence : {verifiees} technologies citées, confrontées au dépôt")

    # --- délégation : lint, typage, tests ------------------------------------

    def deleguer(self) -> None:
        cibles = self.conf.get("cibles_deleguees", [])
        if not cibles:
            self.avertissements.append(
                "Aucune cible déléguée dans .claude/verifier.toml : le lint et le typage "
                "ne sont pas exécutés. Un outil installé mais non branché est une "
                "garde qu'on croit avoir."
            )
            return
        for cible in cibles:
            r = subprocess.run(["make", cible], cwd=self.racine,
                               capture_output=True, text=True)
            if r.returncode:
                self.erreurs.append(
                    f"cible déléguée « make {cible} » en échec :\n"
                    + (r.stdout + r.stderr).strip()[-1500:]
                )
        print(f"== délégation : {len(cibles)} cible(s) — {', '.join(cibles)}")

    # --- le gardien se garde lui-même ----------------------------------------

    def regle_robot_vivant(self) -> None:
        wf = self.racine / ".github" / "workflows" / "synchro-gabarit.yml"
        if not wf.is_file():
            self.avertissements.append(
                "Pas de workflow de synchronisation du gabarit. Sans lui, une "
                "amélioration de ce vérificateur n'atteindra jamais ce dépôt."
            )

    # --- syntaxe des fichiers suivis -----------------------------------------

    def regle_syntaxe(self, suivis: list[str]) -> None:
        nj = npy = nsh = 0
        for s in suivis:
            p = self.racine / s
            if not p.is_file():
                continue
            if p.suffix == ".json":
                nj += 1
                try:
                    json.loads(p.read_text(encoding="utf-8"))
                except Exception as e:  # noqa: BLE001
                    self.erreurs.append(f"{s} : JSON invalide ({e}).")
            elif p.suffix == ".py":
                npy += 1
                try:
                    ast.parse(p.read_text(encoding="utf-8"))
                except SyntaxError as e:
                    self.erreurs.append(f"{s} : Python invalide ({e}).")
            elif p.suffix == ".sh":
                nsh += 1
                if subprocess.run(["bash", "-n", str(p)], capture_output=True).returncode:
                    self.erreurs.append(f"{s} : Bash invalide.")
        print(f"== syntaxe : {nj} JSON, {npy} Python, {nsh} Bash")

    def executer(self) -> int:
        self.regles_statut()
        self.regle_taille()
        self.regle_a_remplir()
        self.regles_liens()
        suivis = self.regle_secrets()
        self.regle_syntaxe(suivis)
        self.regle_coherence_pile()
        self.regle_robot_vivant()
        self.deleguer()

        for a in self.avertissements:
            print(f"\n⚠  {a}")
        if self.erreurs:
            print("\nVERIFIER ÉCHEC")
            for e in self.erreurs:
                print("  ✗", e)
            return 1
        print(f"\nVERIFIER OK · vérificateur v{VERSION} · {len(suivis)} fichiers suivis")
        return 0


def main() -> int:
    racine = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    return Verificateur(racine).executer()


if __name__ == "__main__":
    sys.exit(main())
