"""Offline precision/recall check for the project's lexical RAG retriever.

Run from the repository root with: python scripts/evaluate_rag_retrieval.py
This reads only docs/*.md and does not call Ollama or modify runtime state.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.rag.retrieval import Corpus

# Positive queries are paraphrases of documented topics. `sources` names at
# least one document that contains the answer. Negative queries are outside
# this project's documentation. This small suite is a calibration diagnostic,
# not a production-quality estimate.
POSITIVE = [
    ("payment recovery", "Comment le système vérifie-t-il qu’un paiement fonctionne de nouveau après un incident ?", {"09-RECETTE-RENDU.md", "08-PCA-PRA.md", "02-ARCHITECTURE.md"}),
    ("acceptance proof", "Quelles sont les conditions pour que le script acceptance marque une preuve PASS ?", {"09-RECETTE-RENDU.md"}),
    ("SOPS", "Quel est le rôle de SOPS dans la gestion des secrets ?", {"INSTALL.md", "06-SECURITE.md"}),
    ("container remediation", "Pourquoi ne faut-il pas redémarrer le conteneur pendant une remédiation ?", {"06-SECURITE.md"}),
    ("IP ban", "Comment fonctionne le bannissement temporaire d’une adresse IP ?", {"06-SECURITE.md"}),
    ("residual risks", "Quels sont les principaux risques résiduels du projet ?", {"07-GOUVERNANCE.md"}),
    ("database restore", "Comment restaurer PostgreSQL et mesurer le RTO et le RPO ?", {"08-PCA-PRA.md"}),
    ("ML features", "Quelles variables Prometheus utilise le détecteur ML ?", {"05-ML-RAG.md"}),
    ("WAF audit", "Comment vérifier que le WAF a bloqué une requête et envoyé un audit à Loki ?", {"06-SECURITE.md", "04-ATTAQUE.md"}),
    ("detector alert", "Quelles conditions doivent être réunies avant que le détecteur envoie une alerte ?", {"05-ML-RAG.md", "02-ARCHITECTURE.md"}),
    ("RAG permissions", "Quels outils d’action, socket, base ou secrets de contrôle sont attachés au RAG ?", {"05-ML-RAG.md"}),
    ("RTO definition", "Quelle est la définition du RTO dans le projet ?", {"08-PCA-PRA.md", "09-RECETTE-RENDU.md"}),
    ("backup files", "Quels fichiers sont créés lors d’une sauvegarde de la base ?", {"08-PCA-PRA.md"}),
    ("baseline split", "Comment la baseline ML est-elle séparée entre entraînement et validation ?", {"05-ML-RAG.md"}),
    ("witness transaction", "Que vérifie la transaction témoin après le confinement ?", {"09-RECETTE-RENDU.md", "08-PCA-PRA.md"}),
    ("RAG corpus", "Sur quels documents le RAG effectue-t-il ses recherches ?", {"05-ML-RAG.md"}),
    ("loadbot role", "Quels endpoints API payment sont accessibles au compte loadbot ?", {"03-INTERFACES.md", "02-ARCHITECTURE.md"}),
    ("WAF port", "Quel port expose le WAF et comment tester son filtrage ?", {"03-INTERFACES.md", "INSTALL.md", "06-SECURITE.md"}),
    ("alert conditions", "Quand le détecteur envoie-t-il une alerte au remédiateur ?", {"05-ML-RAG.md", "02-ARCHITECTURE.md"}),
    ("idempotency", "Comment l’idempotence évite-t-elle un double paiement ?", {"03-INTERFACES.md", "VALIDATION.md"}),
]

NEGATIVE = [
    ("sun", "Quelle est la température au cœur du Soleil ?"),
    ("black holes", "Comment se forment les trous noirs ?"),
    ("recipe", "Donne une recette de pâtes carbonara."),
    ("football", "Qui a gagné la Coupe du monde de football en 1998 ?"),
    ("weather", "Quel temps fera-t-il demain à Tokyo ?"),
    ("geometry", "Quelle est la formule de l’aire d’un triangle ?"),
    ("moon", "Quelle est la distance moyenne entre la Terre et la Lune ?"),
    ("Java", "Écris un programme Java qui trie une liste."),
    ("music", "Qui a composé la Neuvième Symphonie ?"),
    ("translation", "Traduis « bonjour » en anglais."),
    ("medicine", "Quel antibiotique prendre contre une angine ?"),
    ("history", "Qui était le premier empereur de Chine ?"),
    ("chemistry", "Quelle est la masse molaire du glucose ?"),
    ("travel", "Quel hôtel choisir à Rome ?"),
    ("sports", "Qui a gagné le dernier championnat NBA ?"),
    ("finance", "Quel est le cours actuel du bitcoin ?"),
    ("art", "Qui a peint Guernica ?"),
    ("language", "Conjugue le verbe avoir au subjonctif."),
    ("geography", "Quelle est la capitale du Pérou ?"),
    ("biology", "Comment fonctionne la photosynthèse ?"),
]


def evaluate(corpus, min_shared_terms):
    positive_recall = sum(
        any(hit["source"] in expected for hit in corpus.retrieve(question, min_shared_terms=min_shared_terms))
        for _, question, expected in POSITIVE
    )
    negative_accepts = sum(
        bool(corpus.retrieve(question, min_shared_terms=min_shared_terms))
        for _, question in NEGATIVE
    )
    return positive_recall, negative_accepts


def main():
    corpus = Corpus(ROOT / "docs")
    print(f"Offline retrieval set: {len(POSITIVE)} relevant, {len(NEGATIVE)} out-of-corpus questions")
    print("Relevant-source recall = a relevant source is present in the top passages.")
    print("False acceptance = at least one passage is returned for an out-of-corpus question.\n")
    for label, overlap in (("Before (cosine only)", 0), ("After (cosine + topic overlap)", 2)):
        recall, false_accepts = evaluate(corpus, overlap)
        print(f"{label}: relevant-source recall {recall}/{len(POSITIVE)}; "
              f"out-of-corpus accepted {false_accepts}/{len(NEGATIVE)}")
    remaining = [name for name, question in NEGATIVE if corpus.retrieve(question)]
    print("Remaining out-of-corpus examples accepted by the gate: " + ", ".join(remaining or ["none"]))
    print("\nThis small, hand-labeled set is diagnostic only; it does not prove semantic grounding or zero hallucinations.")


if __name__ == "__main__":
    main()
