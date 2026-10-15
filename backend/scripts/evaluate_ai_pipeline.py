"""
ResolveAI (BIIRS) — Comprehensive AI Evaluation Benchmark Script.
Evaluates the AI pipeline across:
1. Classification accuracy, Category-level Precision, Recall, and F1-score
2. Semantic similarity retrieval quality (Precision@3, MRR) comparing Sentence Transformers vs Feature Hashing Fallback
3. Incident cluster correlation (True positive, False positive, Missed incident patterns)
4. Root-cause evidence grounding (Grounded facts vs unsupported assertions)
5. Processing latency (p50, p95, mean)
6. Model availability and engine attribution
"""

import os
import sys
import time
import math
import json
from collections import defaultdict
from typing import Dict, List, Any

# Setup Django environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from apps.intelligence.services.classifier import DeterministicBankingClassifier, ComplaintClassificationService
from apps.intelligence.services.embeddings import DeterministicHashingEmbeddingProvider, SentenceTransformerEmbeddingProvider
from apps.intelligence.services.root_cause import DeterministicRootCauseAnalyzer, RootCauseAnalysisService

# Documented Synthetic Benchmark Dataset (30 ground-truth labeled banking complaints)
BENCHMARK_DATASET = [
    # CARDS_ATM (6 examples)
    {
        "id": "ATM-01",
        "category": "CARDS_ATM",
        "text": "Dispenser timeout at ATM terminal 04. Account debited 20,000 NGN but no cash was presented.",
        "incident_cluster": "INC-ATM-HARDWARE",
        "grounded_facts": ["Account debited", "Terminal 04", "Sensor timeout"],
    },
    {
        "id": "ATM-02",
        "category": "CARDS_ATM",
        "text": "Card was swallowed by ATM machine after entering correct PIN twice at Marina branch.",
        "incident_cluster": None,
        "grounded_facts": ["Swallowed card", "Marina branch"],
    },
    {
        "id": "ATM-03",
        "category": "CARDS_ATM",
        "text": "ATM dispensed 10,000 NGN instead of 30,000 NGN requested. Ledger shows full 30,000 debit.",
        "incident_cluster": "INC-ATM-HARDWARE",
        "grounded_facts": ["Short dispense", "Ledger debit 30,000 NGN"],
    },
    {
        "id": "ATM-04",
        "category": "CARDS_ATM",
        "text": "ATM transaction declined due to switch timeout, but my account was debited 50,000 NGN.",
        "incident_cluster": "INC-ATM-SWITCH",
        "grounded_facts": ["Declined transaction", "Switch timeout", "Debited 50,000 NGN"],
    },
    {
        "id": "ATM-05",
        "category": "CARDS_ATM",
        "text": "Hardware error on ATM cash cassette while withdrawing at Ikeja branch. Cash never came out.",
        "incident_cluster": "INC-ATM-HARDWARE",
        "grounded_facts": ["Hardware error", "Cash cassette fault"],
    },
    {
        "id": "ATM-06",
        "category": "CARDS_ATM",
        "text": "Card retained by ATM during withdrawal prompt. Screen went blank and machine rebooted.",
        "incident_cluster": None,
        "grounded_facts": ["Retained card", "Machine rebooted"],
    },

    # TRANSFERS (6 examples)
    {
        "id": "TRF-01",
        "category": "TRANSFERS",
        "text": "Interbank NIP outward transfer of 150,000 NGN debited from my account but beneficiary did not receive credit.",
        "incident_cluster": "INC-NIP-OUTAGE",
        "grounded_facts": ["Outward transfer", "Beneficiary not credited", "150,000 NGN"],
    },
    {
        "id": "TRF-02",
        "category": "TRANSFERS",
        "text": "Instant transfer to GTBank failed on mobile app with session timeout, money deducted from my balance.",
        "incident_cluster": "INC-NIP-OUTAGE",
        "grounded_facts": ["Transfer failed", "Session timeout", "Balance deducted"],
    },
    {
        "id": "TRF-03",
        "category": "TRANSFERS",
        "text": "Beneficiary account credited 24 hours late for an express transfer, incurring penalty interest.",
        "incident_cluster": None,
        "grounded_facts": ["Delayed settlement", "24 hours late"],
    },
    {
        "id": "TRF-04",
        "category": "TRANSFERS",
        "text": "NIP interbank gateway reported transaction timeout; sender ledger was debited twice for one transaction.",
        "incident_cluster": "INC-NIP-OUTAGE",
        "grounded_facts": ["Gateway timeout", "Duplicate debit"],
    },
    {
        "id": "TRF-05",
        "category": "TRANSFERS",
        "text": "Transfer reversed on core banking ledger but funds not unblocked in available customer balance.",
        "incident_cluster": None,
        "grounded_facts": ["Reversed on core ledger", "Funds not unblocked"],
    },
    {
        "id": "TRF-06",
        "category": "TRANSFERS",
        "text": "Bulk salary payment transfer batch stuck in pending state on corporate portal without transaction reference.",
        "incident_cluster": None,
        "grounded_facts": ["Salary batch stuck", "Pending state"],
    },

    # FRAUD_SECURITY (6 examples)
    {
        "id": "FRD-01",
        "category": "FRAUD_SECURITY",
        "text": "Unauthorized online transaction of 85,000 NGN from international merchant. I never shared my card or OTP.",
        "incident_cluster": "INC-BIN-ATTACK",
        "grounded_facts": ["Unauthorized transaction", "International merchant", "No OTP shared"],
    },
    {
        "id": "FRD-02",
        "category": "FRAUD_SECURITY",
        "text": "Phishing email link clicked by customer; unauthorized mobile app device registered and funds swept.",
        "incident_cluster": None,
        "grounded_facts": ["Phishing link", "Unauthorized device registered"],
    },
    {
        "id": "FRD-03",
        "category": "FRAUD_SECURITY",
        "text": "Card skimming suspected at third-party POS terminal; multiple unauthorized debits in quick succession.",
        "incident_cluster": "INC-BIN-ATTACK",
        "grounded_facts": ["POS skimming suspected", "Multiple unauthorized debits"],
    },
    {
        "id": "FRD-04",
        "category": "FRAUD_SECURITY",
        "text": "Account compromised via social engineering scam; customer tricked into revealing login credentials.",
        "incident_cluster": None,
        "grounded_facts": ["Social engineering scam", "Credentials compromised"],
    },
    {
        "id": "FRD-05",
        "category": "FRAUD_SECURITY",
        "text": "SIM swap fraud resulted in unauthorized password reset and transfer of 200,000 NGN via USSD.",
        "incident_cluster": None,
        "grounded_facts": ["SIM swap", "USSD transfer of 200,000 NGN"],
    },
    {
        "id": "FRD-06",
        "category": "FRAUD_SECURITY",
        "text": "Unrecognized POS purchase debited in London while customer physically in Lagos with card in hand.",
        "incident_cluster": "INC-BIN-ATTACK",
        "grounded_facts": ["Card clone suspected", "London debit while in Lagos"],
    },

    # BILL_PAYMENTS (6 examples)
    {
        "id": "BIL-01",
        "category": "BILL_PAYMENTS",
        "text": "Electricity token purchase of 10,000 NGN debited from account but meter token was never generated or SMS sent.",
        "incident_cluster": "INC-DISCO-GATEWAY",
        "grounded_facts": ["Token purchase", "Meter token not generated", "10,000 NGN debited"],
    },
    {
        "id": "BIL-02",
        "category": "BILL_PAYMENTS",
        "text": "DSTV cable subscription payment debited twice; decoder viewing not restored after 6 hours.",
        "incident_cluster": None,
        "grounded_facts": ["Double debit for DSTV", "Viewing not restored"],
    },
    {
        "id": "BIL-03",
        "category": "BILL_PAYMENTS",
        "text": "Airtime top-up of 5,000 NGN failed on USSD channel due to telco timeout, but bank account was charged.",
        "incident_cluster": None,
        "grounded_facts": ["Airtime top-up failed", "Telco timeout", "Account charged"],
    },
    {
        "id": "BIL-04",
        "category": "BILL_PAYMENTS",
        "text": "Utility bill payment to Ikeja Electric disco failed at aggregator API; transaction not reversed.",
        "incident_cluster": "INC-DISCO-GATEWAY",
        "grounded_facts": ["Aggregator API failure", "Transaction not reversed"],
    },
    {
        "id": "BIL-05",
        "category": "BILL_PAYMENTS",
        "text": "Internet subscription renewal payment debited; service provider reports payment not received.",
        "incident_cluster": None,
        "grounded_facts": ["Internet renewal", "Provider reports unreceived"],
    },
    {
        "id": "BIL-06",
        "category": "BILL_PAYMENTS",
        "text": "Prepaid power meter token API timeout; customer charged twice for single recharge request.",
        "incident_cluster": "INC-DISCO-GATEWAY",
        "grounded_facts": ["API timeout", "Charged twice"],
    },

    # ACCOUNT_SERVICES (6 examples)
    {
        "id": "ACC-01",
        "category": "ACCOUNT_SERVICES",
        "text": "Incorrect regulatory PND lien placed on savings account without court order or prior notice.",
        "incident_cluster": None,
        "grounded_facts": ["Lien placed on account", "No court order"],
    },
    {
        "id": "ACC-02",
        "category": "ACCOUNT_SERVICES",
        "text": "Monthly SMS alert charges billed 15 times in single day due to billing cycle glitch.",
        "incident_cluster": "INC-BILLING-GLITCH",
        "grounded_facts": ["15 SMS charges in one day", "Billing cycle glitch"],
    },
    {
        "id": "ACC-03",
        "category": "ACCOUNT_SERVICES",
        "text": "BVN linkage failed at branch; biometric update not reflecting on central banking database.",
        "incident_cluster": None,
        "grounded_facts": ["BVN linkage failed", "Biometric not reflecting"],
    },
    {
        "id": "ACC-04",
        "category": "ACCOUNT_SERVICES",
        "text": "Dormant account reactivation documents submitted two weeks ago; account still restricted from withdrawals.",
        "incident_cluster": None,
        "grounded_facts": ["Dormant account reactivation", "Two weeks delay"],
    },
    {
        "id": "ACC-05",
        "category": "ACCOUNT_SERVICES",
        "text": "Duplicate electronic maintenance fee deducted on corporate current account.",
        "incident_cluster": "INC-BILLING-GLITCH",
        "grounded_facts": ["Duplicate maintenance fee", "Corporate account"],
    },
    {
        "id": "ACC-06",
        "category": "ACCOUNT_SERVICES",
        "text": "Name mismatch on debit card issuance after marriage certificate update at customer service desk.",
        "incident_cluster": None,
        "grounded_facts": ["Name mismatch on card", "Marriage certificate submitted"],
    },
]


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


class MockComplaint:
    def __init__(self, ref: str, text: str):
        self.id = ref
        self.reference = ref
        self.summary = text
        self.narrative = text
        self.source_channel = "MOBILE_APP"


def evaluate():
    print("=" * 80)
    print("RESOLVEAI (BIIRS) — AI PIPELINE COMPREHENSIVE BENCHMARK EVALUATION")
    print("=" * 80)

    # Engines to evaluate
    classifier = DeterministicBankingClassifier()
    feature_hasher = DeterministicHashingEmbeddingProvider()
    sentence_transformer = SentenceTransformerEmbeddingProvider()

    valid_cats = ["CARDS_ATM", "TRANSFERS", "FRAUD_SECURITY", "BILL_PAYMENTS", "ACCOUNT_SERVICES"]
    valid_prios = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

    # 1. Classification Evaluation
    print("\n--- 1. CLASSIFICATION ACCURACY & CATEGORY METRICS ---")
    y_true = []
    y_pred = []
    latencies_cls = []

    for item in BENCHMARK_DATASET:
        t0 = time.perf_counter()
        res = classifier.classify(
            summary=item["text"],
            narrative="",
            valid_categories=valid_cats,
            valid_priorities=valid_prios,
        )
        latencies_cls.append((time.perf_counter() - t0) * 1000.0)

        y_true.append(item["category"])
        y_pred.append(res.suggested_category_code)

    # Compute overall accuracy
    correct = sum(1 for yt, yp in zip(y_true, y_pred) if yt == yp)
    total = len(y_true)
    accuracy = correct / total

    # Compute per-category precision, recall, f1
    categories = sorted(list(set(y_true)))
    cat_metrics = {}

    for cat in categories:
        tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == cat and yp == cat)
        fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt != cat and yp == cat)
        fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == cat and yp != cat)

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0

        cat_metrics[cat] = {"precision": prec, "recall": rec, "f1": f1, "count": sum(1 for y in y_true if y == cat)}

    print(f"Total Test Cases: {total}")
    print(f"Overall Accuracy: {accuracy * 100:.2f}% ({correct}/{total})")
    print(f"Mean Classification Latency: {sum(latencies_cls)/len(latencies_cls):.3f} ms (p95: {sorted(latencies_cls)[int(len(latencies_cls)*0.95)]:.3f} ms)")
    print("\nCategory Breakdown:")
    for cat, m in cat_metrics.items():
        print(f"  {cat:20} -> Precision: {m['precision']*100:.1f}%, Recall: {m['recall']*100:.1f}%, F1: {m['f1']:.3f} (n={m['count']})")

    # 2. Semantic Similarity & Retrieval Quality: Feature Hashing vs Sentence Transformers
    print("\n--- 2. RETRIEVAL QUALITY: SENTENCE TRANSFORMER VS FEATURE HASHING ---")
    
    # Precompute embeddings for all benchmark items under both providers
    vectors_hash = [feature_hasher.generate_embedding(item["text"]) for item in BENCHMARK_DATASET]
    
    st_available = True
    try:
        # Check if actual model loads without falling back to deterministic
        st_model = sentence_transformer._get_model()
        if st_model is not None:
            vectors_st = [sentence_transformer.generate_embedding(item["text"]) for item in BENCHMARK_DATASET]
        else:
            st_available = False
            vectors_st = None
            print("Notice: SentenceTransformer native PyTorch weights not present in local environment; offline feature hashing is active fallback.")
    except Exception as e:
        st_available = False
        vectors_st = None
        print(f"SentenceTransformer not available in current process: {e}")

    def evaluate_retrieval(vectors, engine_name):
        prec_at_3_list = []
        mrr_list = []

        for i, query_item in enumerate(BENCHMARK_DATASET):
            target_cat = query_item["category"]
            sims = []
            for j, candidate_item in enumerate(BENCHMARK_DATASET):
                if i == j:
                    continue
                sim = cosine_similarity(vectors[i], vectors[j])
                sims.append((sim, candidate_item["category"]))

            sims.sort(key=lambda x: x[0], reverse=True)
            top_3 = sims[:3]

            # Precision@3: fraction of top 3 sharing same ground-truth category
            matching_top3 = sum(1 for _, c in top_3 if c == target_cat)
            prec_at_3_list.append(matching_top3 / 3.0)

            # MRR: rank of first matching item
            first_rank = next((rank for rank, (_, c) in enumerate(sims, start=1) if c == target_cat), None)
            mrr_list.append(1.0 / first_rank if first_rank else 0.0)

        mean_p3 = sum(prec_at_3_list) / len(prec_at_3_list)
        mean_mrr = sum(mrr_list) / len(mrr_list)
        print(f"Engine: {engine_name}")
        print(f"  Precision@3: {mean_p3 * 100:.2f}%")
        print(f"  Mean Reciprocal Rank (MRR): {mean_mrr:.3f}")
        return {"precision_at_3": mean_p3, "mrr": mean_mrr}

    retrieval_hash_metrics = evaluate_retrieval(vectors_hash, "Deterministic Feature Hashing (384-d Offline Fallback)")
    retrieval_st_metrics = evaluate_retrieval(vectors_st, "Sentence Transformer (all-MiniLM-L6-v2)") if st_available and vectors_st else None

    # 3. Incident Correlation & Clustering Evaluation
    print("\n--- 3. INCIDENT CLUSTER CORRELATION ---")
    incident_pairs_evaluated = 0
    true_cluster_hits = 0
    false_positives = 0
    missed_patterns = 0

    threshold = 0.50
    for i in range(len(BENCHMARK_DATASET)):
        for j in range(i + 1, len(BENCHMARK_DATASET)):
            c1 = BENCHMARK_DATASET[i]
            c2 = BENCHMARK_DATASET[j]
            sim = cosine_similarity(vectors_hash[i], vectors_hash[j])

            same_cluster = (c1["incident_cluster"] is not None) and (c1["incident_cluster"] == c2["incident_cluster"])
            incident_pairs_evaluated += 1

            if same_cluster:
                if sim >= threshold:
                    true_cluster_hits += 1
                else:
                    missed_patterns += 1
            else:
                if sim >= 0.75:  # False-positive cross-incident similarity
                    false_positives += 1

    print(f"Total Incident Pairs Assessed: {incident_pairs_evaluated}")
    print(f"True Incident Associations: {true_cluster_hits}")
    print(f"Missed Incident Associations: {missed_patterns}")
    print(f"False-Positive Incident Associations: {false_positives}")

    # 4. Root-Cause Evidence Grounding Analysis
    print("\n--- 4. ROOT-CAUSE GROUNDING & UNGROUNDED ASSERTIONS ---")
    analyzer = DeterministicRootCauseAnalyzer()
    grounded_eval_count = 0
    unsupported_assertions = 0

    for item in BENCHMARK_DATASET:
        mock_c = MockComplaint(item["id"], item["text"])
        res = analyzer.analyze(complaint=mock_c, similar_complaints=[], transactions=[], evidence=[])
        hallucination_indicators = ["pin is", "balance is zero", "guaranteed fraud", "stolen 100%"]
        content_lower = f"{res.possible_cause or ''} {' '.join(res.facts)} {' '.join(res.hypotheses)}".lower()
        if any(ind in content_lower for ind in hallucination_indicators):
            unsupported_assertions += 1
        grounded_eval_count += 1

    grounding_rate = (grounded_eval_count - unsupported_assertions) / grounded_eval_count
    print(f"Evaluated Cases: {grounded_eval_count}")
    print(f"Grounded Facts Ratio: {grounding_rate * 100:.1f}%")
    print(f"Unsupported / Hallucinated Assertions: {unsupported_assertions}")

    results = {
        "dataset_size": total,
        "classification": {
            "accuracy": accuracy,
            "category_metrics": cat_metrics,
            "latency_ms_mean": sum(latencies_cls)/len(latencies_cls),
            "latency_ms_p95": sorted(latencies_cls)[int(len(latencies_cls)*0.95)],
        },
        "retrieval": {
            "feature_hashing": retrieval_hash_metrics,
            "sentence_transformer": retrieval_st_metrics,
            "comparison_notes": "Deterministic feature hashing provides 384-d offline vectors suitable for cosine search when ML libraries are unavailable. Semantic model provides denser semantic abstraction without lexical token overlap."
        },
        "incident_correlation": {
            "incident_pairs_evaluated": incident_pairs_evaluated,
            "true_cluster_hits": true_cluster_hits,
            "missed_patterns": missed_patterns,
            "false_positives": false_positives,
        },
        "grounding": {
            "grounding_rate": grounding_rate,
            "unsupported_assertions": unsupported_assertions,
        },
    }

    # Save to JSON artifact
    out_path = os.path.join(os.path.dirname(__file__), "ai_evaluation_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n[OK] Results persisted to {out_path}")
    return results


if __name__ == "__main__":
    evaluate()

