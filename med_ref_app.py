import streamlit as st
import requests
import math
import re
import html
from datetime import datetime
from itertools import combinations
from typing import Dict, Any, Optional, List, Tuple

st.set_page_config(
    page_title="Clinical Indication-Driven Dosing & Interaction System",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    .warning-box { background-color: #fff3cd; border-left: 6px solid #ffecb5; padding: 15px; border-radius: 5px; color: #664d03; margin-bottom: 20px; }
    .boxed-warning { background-color: #f8d7da; border-left: 6px solid #dc3545; padding: 15px; border-radius: 5px; color: #842029; margin-bottom: 20px; }
    .interaction-high { background-color: #f8d7da; border-left: 6px solid #dc3545; padding: 12px 15px; border-radius: 5px; color: #842029; margin-bottom: 12px; }
    .interaction-moderate { background-color: #fff3cd; border-left: 6px solid #ffc107; padding: 12px 15px; border-radius: 5px; color: #664d03; margin-bottom: 12px; }
    .interaction-clear { background-color: #d1e7dd; border-left: 6px solid #198754; padding: 12px 15px; border-radius: 5px; color: #0f5132; margin-bottom: 12px; }
    .counseling-box { background-color: #e0f2fe; border-left: 6px solid #0284c7; padding: 15px; border-radius: 5px; color: #075985; margin-top: 15px; }
    .formula-box { background-color: #f8fafc; border: 1px solid #cbd5e1; padding: 12px 15px; border-radius: 5px; color: #334155; margin-bottom: 12px; font-size: 0.9em; }
    .source-box { background-color: #f0fdf4; border: 1px solid #bbf7d0; padding: 10px 15px; border-radius: 5px; color: #166534; margin-bottom: 15px; font-size: 0.88em; }
    .source-box a { color: #15803d; font-weight: 600; text-decoration: underline; }
    </style>
""", unsafe_allow_html=True)

class DrugDataClient:
    OPENFDA_URL = "https://api.fda.gov/drug/label.json"
    RXNORM_URL = "https://rxnav.nlm.nih.gov/REST"

    @staticmethod
    @st.cache_data(ttl=3600, show_spinner=False)
    def resolve_rxnorm_ingredient(drug_name: str) -> Dict[str, str]:
        clean_name = drug_name.strip()
        result = {"input": clean_name, "rxcui": "N/A", "normalized_name": clean_name.lower()}
        try:
            resp = requests.get(
                f"{DrugDataClient.RXNORM_URL}/approximateTerm.json",
                params={"term": clean_name, "maxEntries": 1},
                timeout=6
            )
            if resp.status_code == 200:
                candidates = resp.json().get("approximateGroup", {}).get("candidate", [])
                if candidates:
                    rxcui = candidates[0].get("rxcui")
                    result["rxcui"] = rxcui
                    prop_resp = requests.get(f"{DrugDataClient.RXNORM_URL}/rxcui/{rxcui}/properties.json", timeout=6)
                    if prop_resp.status_code == 200:
                        prop_name = prop_resp.json().get("properties", {}).get("name")
                        if prop_name:
                            result["normalized_name"] = prop_name.lower()
        except requests.RequestException:
            pass
        return result

    @staticmethod
    @st.cache_data(ttl=3600, show_spinner=False)
    def fetch_drug_label(drug_name: str) -> Optional[Dict[str, Any]]:
        clean_name = drug_name.strip().lower()
        if not clean_name:
            return None

        queries = [
            f'openfda.generic_name:"{clean_name}"',
            f'openfda.brand_name:"{clean_name}"',
            f'active_ingredient:"{clean_name}"'
        ]

        for query in queries:
            try:
                params = {"search": query, "limit": 1}
                response = requests.get(DrugDataClient.OPENFDA_URL, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if "results" in data and len(data["results"]) > 0:
                        return DrugDataClient._parse_label_data(data["results"][0])
            except requests.RequestException:
                continue
        return None

    @staticmethod
    def _extract_field(raw_data: Dict[str, Any], field_name: str, default: str = "Not specified in official FDA label.") -> str:
        content = raw_data.get(field_name)
        if isinstance(content, list) and len(content) > 0:
            return "\n\n".join(content)
        return default

    @staticmethod
    def _parse_label_data(result: Dict[str, Any]) -> Dict[str, Any]:
        openfda = result.get("openfda", {})
        
        def get_openfda_list(key: str) -> List[str]:
            items = openfda.get(key, [])
            return list(set(items)) if items else []

        generic_list = get_openfda_list("generic_name")
        brand_list = get_openfda_list("brand_name")
        class_list = get_openfda_list("pharm_class_epc") + get_openfda_list("pharm_class_FM")

        return {
            "brand_name": ", ".join(brand_list) if brand_list else "N/A",
            "generic_name": ", ".join(generic_list) if generic_list else "N/A",
            "generic_list": [g.lower() for g in generic_list],
            "brand_list": [b.lower() for b in brand_list],
            "class_list": [c.lower() for c in class_list],
            "manufacturer": ", ".join(get_openfda_list("manufacturer_name")) or "N/A",
            "route": ", ".join(get_openfda_list("route")) or "N/A",
            "pharm_class": ", ".join(get_openfda_list("pharm_class_epc")) or "N/A",
            "boxed_warning": DrugDataClient._extract_field(result, "boxed_warning", default=""),
            "indications": DrugDataClient._extract_field(result, "indications_and_usage"),
            "dosage_and_admin": DrugDataClient._extract_field(result, "dosage_and_administration"),
            "contraindications": DrugDataClient._extract_field(result, "contraindications"),
            "warnings": DrugDataClient._extract_field(result, "warnings_and_cautions", 
                                                     DrugDataClient._extract_field(result, "warnings")),
            "interactions": DrugDataClient._extract_field(result, "drug_interactions"),
            "adverse_reactions": DrugDataClient._extract_field(result, "adverse_reactions"),
            "specific_populations": DrugDataClient._extract_field(result, "use_in_specific_populations"),
            "overdosage": DrugDataClient._extract_field(result, "overdosage"),
            "mechanism": DrugDataClient._extract_field(result, "mechanism_of_action"),
        }

class PairwiseInteractionEngine:
    CLASS_KEYWORD_MAP = {
        "nsaid": ["ibuprofen", "naproxen", "diclofenac", "celecoxib", "meloxicam", "ketorolac", "indomethacin", "aspirin"],
        "anticoagulant": ["warfarin", "apixaban", "rivaroxaban", "dabigatran", "edoxaban", "heparin", "enoxaparin"],
        "antiplatelet": ["aspirin", "clopidogrel", "prasugrel", "ticagrelor"],
        "ace inhibitor": ["lisinopril", "enalapril", "ramipril", "benazepril", "captopril", "perindopril"],
        "arb": ["losartan", "valsartan", "irbesartan", "olmesartan", "candesartan", "telmisartan"],
        "potassium-sparing diuretic": ["spironolactone", "eplerenone", "amiloride", "triamterene"],
        "loop diuretic": ["furosemide", "bumetanide", "torsemide"],
        "macrolide": ["clarithromycin", "erythromycin", "azithromycin"],
        "fluoroquinolone": ["ciprofloxacin", "levofloxacin", "moxifloxacin"],
        "statin": ["simvastatin", "atorvastatin", "rosuvastatin", "pravastatin", "lovastatin"],
        "ssri": ["fluoxetine", "sertraline", "paroxetine", "citalopram", "escitalopram"],
        "snri": ["venlafaxine", "duloxetine", "desvenlafaxine"],
        "maoi": ["phenelzine", "tranylcypromine", "selegiline", "linezolid"],
        "opioid": ["morphine", "oxycodone", "hydrocodone", "fentanyl", "tramadol", "codeine", "methadone"],
        "benzodiazepine": ["alprazolam", "lorazepam", "diazepam", "clonazepam", "midazolam"],
        "nitrate": ["nitroglycerin", "isosorbide mononitrate", "isosorbide dinitrate"],
        "pde5 inhibitor": ["sildenafil", "tadalafil", "vardenafil"],
        "cyp3a4 inhibitor": ["clarithromycin", "erythromycin", "ketoconazole", "itraconazole", "ritonavir", "diltiazem", "verapamil"],
        "ppi": ["omeprazole", "pantoprazole", "lansoprazole", "esomeprazole", "rabeprazole"],
        "h2ra": ["famotidine", "ranitidine", "cimetidine", "nizatidine"],
    }

    CURATED_CLINICAL_RULES = [
        {
            "group_a": ["warfarin", "apixaban", "rivaroxaban", "dabigatran"],
            "group_b": ["ibuprofen", "naproxen", "diclofenac", "ketorolac", "meloxicam", "aspirin", "ciprofloxacin", "clarithromycin", "erythromycin", "sulfamethoxazole", "trimethoprim", "metronidazole"],
            "severity": "Major / High Risk",
            "summary": "Increased risk of serious bleeding due to CYP2C9/3A4 inhibition or additive mucosal/antiplatelet injury."
        },
        {
            "group_a": ["sildenafil", "tadalafil", "vardenafil"],
            "group_b": ["nitroglycerin", "isosorbide mononitrate", "isosorbide dinitrate"],
            "severity": "Contraindicated",
            "summary": "Synergistic vasodilation via nitric oxide-cGMP causes profound, life-threatening hypotension."
        },
        {
            "group_a": ["simvastatin", "lovastatin", "atorvastatin"],
            "group_b": ["clarithromycin", "erythromycin", "itraconazole", "ketoconazole", "gemfibrozil"],
            "severity": "Contraindicated / Major",
            "summary": "Potent CYP3A4/OATP1B1 inhibition markedly elevates statin concentrations, risking rhabdomyolysis."
        },
        {
            "group_a": ["lisinopril", "enalapril", "ramipril", "losartan", "valsartan"],
            "group_b": ["spironolactone", "eplerenone", "amiloride", "triamterene", "potassium chloride", "trimethoprim"],
            "severity": "Major / Monitor Closely",
            "summary": "Additive hyperkalemic effects. Concurrent use elevates risk of severe hyperkalemia."
        },
        {
            "group_a": ["fluoxetine", "sertraline", "paroxetine", "citalopram", "escitalopram", "venlafaxine", "duloxetine"],
            "group_b": ["phenelzine", "tranylcypromine", "selegiline", "linezolid", "tramadol", "sumatriptan", "metoclopramide"],
            "severity": "Major / Serotonin Syndrome Risk",
            "summary": "Concurrent serotonergic agents significantly elevate risk of fatal serotonin syndrome or extrapyramidal reactions."
        },
        {
            "group_a": ["morphine", "oxycodone", "hydrocodone", "fentanyl", "methadone", "tramadol"],
            "group_b": ["alprazolam", "lorazepam", "diazepam", "clonazepam", "zolpidem", "promethazine", "ketotifen", "diphenhydramine", "hydroxyzine", "chlorpheniramine"],
            "severity": "Major (Boxed Warning / CNS Depression)",
            "summary": "Concomitant use of opioids with CNS depressants or sedating antihistamines may result in profound sedation and respiratory depression."
        },
        {
            "group_a": ["methotrexate"],
            "group_b": ["amoxicillin", "penicillin", "ampicillin", "piperacillin", "cefixime", "cefaclor", "ibuprofen", "naproxen", "diclofenac", "trimethoprim", "sulfamethoxazole", "omeprazole", "lansoprazole"],
            "severity": "Major",
            "summary": "Reduced renal tubular clearance or additive folate antagonism causes severe methotrexate hematologic/mucosal toxicity."
        },
        {
            "group_a": ["ciprofloxacin", "levofloxacin", "moxifloxacin", "domperidone"],
            "group_b": ["theophylline", "tizanidine", "amiodarone", "ondansetron", "clarithromycin", "erythromycin", "azithromycin", "hydroxyzine"],
            "severity": "Major / Contraindicated",
            "summary": "Additive QTc prolongation or potent CYP3A4/CYP1A2 inhibition resulting in severe toxicity or ventricular arrhythmias (Torsades de Pointes)."
        }
    ]

    @classmethod
    def get_search_terms_for_drug(cls, drug_profile: Dict[str, Any]) -> List[str]:
        terms = set()
        norm_name = drug_profile["rxnorm"]["normalized_name"]
        terms.add(norm_name)
        
        first_token = norm_name.split()[0]
        if len(first_token) > 3:
            terms.add(first_token)

        if drug_profile.get("fda_data"):
            for g in drug_profile["fda_data"].get("generic_list", []):
                terms.add(g)
                if len(g.split()[0]) > 3:
                    terms.add(g.split()[0])
            for b in drug_profile["fda_data"].get("brand_list", []):
                if len(b) > 3:
                    terms.add(b)

        for class_name, members in cls.CLASS_KEYWORD_MAP.items():
            if any(m in norm_name or norm_name in m for m in members):
                terms.add(class_name)

        return sorted(list(terms), key=len, reverse=True)

    @staticmethod
    def extract_matching_sentences(text: str, search_terms: List[str], max_snippets: int = 3) -> List[str]:
        if not text or "Not specified" in text:
            return []

        sentences = re.split(r'(?<=[.!?])\s+|\n+', text)
        matches = []

        for sentence in sentences:
            clean_s = sentence.strip()
            if len(clean_s) < 20 or len(clean_s) > 650:
                continue
            for term in search_terms:
                pattern = rf'\b{re.escape(term)}s?\b'
                if re.search(pattern, clean_s, flags=re.IGNORECASE):
                    highlighted = re.sub(
                        pattern,
                        lambda m: f"**{m.group(0)}**",
                        clean_s,
                        flags=re.IGNORECASE
                    )
                    if highlighted not in matches:
                        matches.append(highlighted)
                    break
            if len(matches) >= max_snippets:
                break

        return matches

    @classmethod
    def evaluate_pair(cls, drug_a: Dict[str, Any], drug_b: Dict[str, Any]) -> Dict[str, Any]:
        name_a = drug_a["rxnorm"]["normalized_name"]
        name_b = drug_b["rxnorm"]["normalized_name"]

        findings = []
        severity = "None Detected"
        severity_rank = 0

        for rule in cls.CURATED_CLINICAL_RULES:
            a_in_1 = any(x in name_a for x in rule["group_a"]) and any(y in name_b for y in rule["group_b"])
            a_in_2 = any(x in name_b for x in rule["group_a"]) and any(y in name_a for y in rule["group_b"])
            if a_in_1 or a_in_2:
                severity = rule["severity"]
                severity_rank = 2
                findings.append({
                    "source": "Clinical Pharmacotherapy Rule",
                    "excerpt": f"**{rule['severity']}:** {rule['summary']}"
                })

        terms_a = cls.get_search_terms_for_drug(drug_a)
        terms_b = cls.get_search_terms_for_drug(drug_b)

        if drug_a.get("fda_data"):
            fda_a = drug_a["fda_data"]
            contra_hits_a = cls.extract_matching_sentences(fda_a["contraindications"], terms_b, max_snippets=2)
            inter_hits_a = cls.extract_matching_sentences(fda_a["interactions"], terms_b, max_snippets=3)
            warn_hits_a = cls.extract_matching_sentences(fda_a["warnings"], terms_b, max_snippets=2)

            if contra_hits_a:
                severity_rank = max(severity_rank, 2)
                if severity == "None Detected":
                    severity = "Contraindicated / Major"
                for h in contra_hits_a:
                    findings.append({"source": f"{name_a.title()} FDA Label (Contraindications)", "excerpt": h})

            for h in inter_hits_a + warn_hits_a:
                if any(k in h.lower() for k in ["contraindicat", "avoid concomitant", "life-threatening", "fatal", "serious bleeding", "rhabdomyolysis"]):
                    severity_rank = max(severity_rank, 2)
                    if severity == "None Detected":
                        severity = "Major Interaction"
                else:
                    severity_rank = max(severity_rank, 1)
                    if severity == "None Detected":
                        severity = "Moderate / Precaution"
                findings.append({"source": f"{name_a.title()} FDA Label (Interactions/Warnings)", "excerpt": h})

        if drug_b.get("fda_data"):
            fda_b = drug_b["fda_data"]
            contra_hits_b = cls.extract_matching_sentences(fda_b["contraindications"], terms_a, max_snippets=2)
            inter_hits_b = cls.extract_matching_sentences(fda_b["interactions"], terms_a, max_snippets=3)
            warn_hits_b = cls.extract_matching_sentences(fda_b["warnings"], terms_a, max_snippets=2)

            if contra_hits_b:
                severity_rank = max(severity_rank, 2)
                if severity == "None Detected":
                    severity = "Contraindicated / Major"
                for h in contra_hits_b:
                    findings.append({"source": f"{name_b.title()} FDA Label (Contraindications)", "excerpt": h})

            for h in inter_hits_b + warn_hits_b:
                if any(k in h.lower() for k in ["contraindicat", "avoid concomitant", "life-threatening", "fatal", "serious bleeding", "rhabdomyolysis"]):
                    severity_rank = max(severity_rank, 2)
                    if severity == "None Detected":
                        severity = "Major Interaction"
                else:
                    severity_rank = max(severity_rank, 1)
                    if severity == "None Detected":
                        severity = "Moderate / Precaution"
                findings.append({"source": f"{name_b.title()} FDA Label (Interactions/Warnings)", "excerpt": h})

        return {
            "pair": f"{name_a.title()} + {name_b.title()}",
            "drug_a": name_a.title(),
            "drug_b": name_b.title(),
            "severity": severity,
            "severity_rank": severity_rank,
            "findings": findings
        }

class PediatricWeightValidator:
    REFERENCE_GROWTH_TABLE: List[Tuple[float, float, float, float]] = [
        (0.0,   2.5,  3.4,  4.4), (1.0,   3.4,  4.4,  5.7), (2.0,   4.3,  5.4,  6.9), (3.0,   5.0,  6.2,  7.8),
        (6.0,   6.2,  7.6,  9.5), (9.0,   7.0,  8.6, 10.7), (12.0,  7.6,  9.4, 11.6), (18.0,  8.6, 10.7, 13.3),
        (24.0,  9.6, 12.0, 15.0), (36.0, 11.2, 14.1, 17.8), (48.0, 12.6, 16.2, 20.8), (60.0, 14.1, 18.3, 24.2),
        (72.0, 15.8, 20.7, 28.0), (84.0, 17.5, 23.2, 32.5), (96.0, 19.3, 25.8, 37.5), (108.0, 21.2, 28.8, 43.2),
        (120.0, 23.3, 32.2, 49.5), (144.0, 28.5, 40.8, 63.5), (168.0, 36.0, 51.0, 77.0), (192.0, 43.0, 58.5, 86.0),
        (216.0, 47.5, 63.5, 92.0),
    ]

    @classmethod
    def get_interpolated_bounds(cls, age_months: float) -> Tuple[float, float, float]:
        table = cls.REFERENCE_GROWTH_TABLE
        if age_months <= table[0][0]:
            return table[0][1], table[0][2], table[0][3]
        if age_months >= table[-1][0]:
            return table[-1][1], table[-1][2], table[-1][3]

        for i in range(len(table) - 1):
            m0, p3_0, p50_0, p97_0 = table[i]
            m1, p3_1, p50_1, p97_1 = table[i + 1]
            if m0 <= age_months <= m1:
                ratio = (age_months - m0) / (m1 - m0) if m1 > m0 else 0.0
                p3 = p3_0 + ratio * (p3_1 - p3_0)
                p50 = p50_0 + ratio * (p50_1 - p50_0)
                p97 = p97_0 + ratio * (p97_1 - p97_0)
                return p3, p50, p97

        return table[-1][1], table[-1][2], table[-1][3]

    @classmethod
    def validate_pediatric_weight(cls, age_value: float, age_unit: str, weight_kg: float) -> Dict[str, Any]:
        age_months = age_value * 12.0 if age_unit == "Years" else age_value
        p3, p50, p97 = cls.get_interpolated_bounds(age_months)

        extreme_low = p3 * 0.55
        extreme_high = p97 * 1.65

        status = "normal"
        messages = []

        weight_if_entered_in_lbs = weight_kg / 2.20462
        weight_if_entered_in_kg = weight_kg * 2.20462

        if weight_kg < extreme_low:
            status = "critical"
            unit_hint = f" Possible Unit Error Detected: Converting {weight_kg:.1f} from lbs yields {weight_if_entered_in_kg:.1f} kg (normal range)." if (p3 <= weight_if_entered_in_kg <= p97) else ""
            messages.append(f"🛑 CLINICALLY IMPLAUSIBLE LOW WEIGHT: Entered weight ({weight_kg:.2f} kg) is critically below the 3rd percentile ({p3:.1f} kg).{unit_hint}")
        elif weight_kg > extreme_high:
            status = "critical"
            unit_hint = f" Possible lb/kg Unit Reversal: {weight_kg:.1f} lbs equals {weight_if_entered_in_lbs:.1f} kg (normal range). Dosing on {weight_kg:.1f} kg instead would cause a 2.2-fold overdose!" if (p3 <= weight_if_entered_in_lbs <= p97) else ""
            messages.append(f"🛑 CLINICALLY IMPLAUSIBLE HIGH WEIGHT: Entered weight ({weight_kg:.2f} kg) drastically exceeds the 97th percentile ({p97:.1f} kg).{unit_hint}")
        elif weight_kg < p3:
            status = "warning"
            messages.append(f"⚠️ Low Weight-for-Age (< 3rd Percentile): Entered weight ({weight_kg:.2f} kg) is below the 3rd percentile ({p3:.1f} kg).")
        elif weight_kg > p97:
            status = "warning"
            messages.append(f"⚠️ High Weight-for-Age (> 97th Percentile): Entered weight ({weight_kg:.2f} kg) exceeds the 97th percentile ({p97:.1f} kg).")

        pct_of_median = (weight_kg / p50) * 100.0 if p50 > 0 else 0.0

        return {
            "age_display": f"{age_value:g} {age_unit.lower()}",
            "age_months": age_months,
            "p3_kg": p3,
            "p50_kg": p50,
            "p97_kg": p97,
            "pct_of_median": pct_of_median,
            "status": status,
            "messages": messages
        }

class IndicationDosingEngine:
    GUIDELINES = {
        # =====================================================================
        # CATEGORY 1: ANTIBIOTICS
        # =====================================================================
        "Amoxicillin": {
            "category": "Antibiotics",
            "sources": [
                {"title": "AAP Clinical Practice Guideline: Acute Otitis Media", "url": "https://doi.org/10.1542/peds.2012-3488"},
                {"title": "IDSA Guideline: Group A Streptococcal Pharyngitis", "url": "https://doi.org/10.1093/cid/cis629"},
                {"title": "DailyMed FDA Label: Amoxicillin", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=AMOXICILLIN"}
            ],
            "indications": {
                "Acute Otitis Media / Sinusitis (Standard Dose: 45 mg/kg/day Q12H)": {"dose_mg_kg_day": 45.0, "freq": 2, "max_single": 875.0, "max_daily": 1750.0},
                "Acute Otitis Media / CAP (High Dose: 90 mg/kg/day Q12H)": {"dose_mg_kg_day": 90.0, "freq": 2, "max_single": 2000.0, "max_daily": 4000.0},
                "Streptococcal Pharyngitis (Divided: 50 mg/kg/day Q12H)": {"dose_mg_kg_day": 50.0, "freq": 2, "max_single": 500.0, "max_daily": 1000.0},
                "Streptococcal Pharyngitis (Once Daily: 50 mg/kg/day Q24H)": {"dose_mg_kg_day": 50.0, "freq": 1, "max_single": 1000.0, "max_daily": 1000.0}
            },
            "forms": {
                "Oral Suspension 400 mg / 5 mL": {"type": "liquid", "conc_mg": 400, "conc_ml": 5},
                "Oral Suspension 250 mg / 5 mL": {"type": "liquid", "conc_mg": 250, "conc_ml": 5},
                "Oral Suspension 125 mg / 5 mL": {"type": "liquid", "conc_mg": 125, "conc_ml": 5},
                "Chewable Tablet 250 mg": {"type": "solid", "strength_mg": 250, "unit": "tablet"},
                "Oral Capsule 500 mg": {"type": "solid", "strength_mg": 500, "unit": "capsule"},
                "Oral Tablet 875 mg": {"type": "solid", "strength_mg": 875, "unit": "tablet"}
            },
            "counseling": [
                "Can be taken with or without food. Taking with food decreases GI upset.",
                "Complete the full prescribed course even if symptoms resolve early.",
                "Shake suspension well before each dose; refrigerate (if preferred for taste) and discard after 14 days."
            ]
        },
        "Amoxicillin-Clavulanate (Augmentin)": {
            "category": "Antibiotics",
            "sources": [
                {"title": "AAP Guideline: Acute Bacterial Sinusitis & AOM", "url": "https://doi.org/10.1542/peds.2013-1071"},
                {"title": "DailyMed FDA Label: Augmentin ES-600 / 400", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=AMOXICILLIN+AND+CLAVULANATE"}
            ],
            "indications": {
                "Acute Otitis Media / Sinusitis (High Dose ES 14:1 — 90 mg/kg/day Q12H)": {"dose_mg_kg_day": 90.0, "freq": 2, "max_single": 2000.0, "max_daily": 4000.0},
                "Standard Infections (7:1 Formulation — 45 mg/kg/day Q12H)": {"dose_mg_kg_day": 45.0, "freq": 2, "max_single": 875.0, "max_daily": 1750.0},
                "Bite Wounds / Skin Infection (40 mg/kg/day Q8H)": {"dose_mg_kg_day": 40.0, "freq": 3, "max_single": 500.0, "max_daily": 1500.0}
            },
            "forms": {
                "Oral Suspension 600 mg / 5 mL (Augmentin ES 14:1)": {"type": "liquid", "conc_mg": 600, "conc_ml": 5},
                "Oral Suspension 400 mg / 5 mL (7:1 Ratio)": {"type": "liquid", "conc_mg": 400, "conc_ml": 5},
                "Oral Suspension 250 mg / 5 mL (4:1 Ratio)": {"type": "liquid", "conc_mg": 250, "conc_ml": 5},
                "Oral Suspension 457 mg / 5 mL (400 mg Amox / 5 mL)": {"type": "liquid", "conc_mg": 400, "conc_ml": 5},
                "Oral Tablet 875 mg / 125 mg": {"type": "solid", "strength_mg": 875, "unit": "tablet"},
                "Oral Tablet 500 mg / 125 mg": {"type": "solid", "strength_mg": 500, "unit": "tablet"}
            },
            "counseling": [
                "Administer at the start of a meal to enhance clavulanate absorption and minimize diarrhea.",
                "Dosing is calculated exclusively on the Amoxicillin component.",
                "Refrigerate reconstituted suspension, shake well, and discard after 10 days."
            ]
        },
        "Cefixime (Suprax)": {
            "category": "Antibiotics",
            "sources": [
                {"title": "AAP Clinical Practice Guideline: Febrile Infant UTI", "url": "https://doi.org/10.1542/peds.2016-3026"},
                {"title": "DailyMed FDA Label: Cefixime (Suprax)", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=CEFIXIME"}
            ],
            "indications": {
                "Uncomplicated UTI / Otitis Media (Once Daily: 8 mg/kg/day Q24H)": {"dose_mg_kg_day": 8.0, "freq": 1, "max_single": 400.0, "max_daily": 400.0},
                "Acute Otitis Media / Pharyngitis (Divided: 8 mg/kg/day Q12H)": {"dose_mg_kg_day": 8.0, "freq": 2, "max_single": 200.0, "max_daily": 400.0}
            },
            "forms": {
                "Oral Suspension 100 mg / 5 mL": {"type": "liquid", "conc_mg": 100, "conc_ml": 5},
                "Oral Suspension 200 mg / 5 mL": {"type": "liquid", "conc_mg": 200, "conc_ml": 5},
                "Oral Capsule 400 mg": {"type": "solid", "strength_mg": 400, "unit": "capsule"}
            },
            "counseling": [
                "May be taken with or without food.",
                "Oral suspension achieves 25–50% higher peak concentrations than tablets; always use suspension when treating otitis media.",
                "Store reconstituted suspension at room temperature or refrigerated; discard after 14 days."
            ]
        },
        "Cefaclor (Ceclor)": {
            "category": "Antibiotics",
            "sources": [
                {"title": "DailyMed FDA Label: Cefaclor Oral Suspension", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=CEFACLOR"}
            ],
            "indications": {
                "Mild-to-Moderate Infections / Pharyngitis (20 mg/kg/day Q8H)": {"dose_mg_kg_day": 20.0, "freq": 3, "max_single": 250.0, "max_daily": 1000.0},
                "Severe Infections / Acute Otitis Media (40 mg/kg/day Q8H)": {"dose_mg_kg_day": 40.0, "freq": 3, "max_single": 333.3, "max_daily": 1000.0},
                "Acute Otitis Media / Pharyngitis (Alternative BID: 40 mg/kg/day Q12H)": {"dose_mg_kg_day": 40.0, "freq": 2, "max_single": 500.0, "max_daily": 1000.0}
            },
            "forms": {
                "Oral Suspension 125 mg / 5 mL": {"type": "liquid", "conc_mg": 125, "conc_ml": 5},
                "Oral Suspension 250 mg / 5 mL": {"type": "liquid", "conc_mg": 250, "conc_ml": 5},
                "Oral Suspension 375 mg / 5 mL": {"type": "liquid", "conc_mg": 375, "conc_ml": 5},
                "Oral Capsule 250 mg": {"type": "solid", "strength_mg": 250, "unit": "capsule"},
                "Oral Capsule 500 mg": {"type": "solid", "strength_mg": 500, "unit": "capsule"}
            },
            "counseling": [
                "May be taken with food to minimize stomach upset.",
                "Refrigerate suspension between doses, shake well, and discard after 14 days."
            ]
        },
        "Cefuroxime Axetil (Zinnat / Ceftin)": {
            "category": "Antibiotics",
            "sources": [
                {"title": "AAP Guideline: Acute Otitis Media (Penicillin Allergy Alternative)", "url": "https://doi.org/10.1542/peds.2012-3488"},
                {"title": "DailyMed FDA Label: Cefuroxime Axetil", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=CEFUROXIME+AXETIL"}
            ],
            "indications": {
                "Acute Otitis Media / Bacterial Sinusitis (30 mg/kg/day Q12H)": {"dose_mg_kg_day": 30.0, "freq": 2, "max_single": 500.0, "max_daily": 1000.0},
                "Pharyngitis / Tonsillitis (20 mg/kg/day Q12H)": {"dose_mg_kg_day": 20.0, "freq": 2, "max_single": 250.0, "max_daily": 500.0}
            },
            "forms": {
                "Oral Suspension 125 mg / 5 mL": {"type": "liquid", "conc_mg": 125, "conc_ml": 5},
                "Oral Suspension 250 mg / 5 mL": {"type": "liquid", "conc_mg": 250, "conc_ml": 5},
                "Oral Tablet 250 mg": {"type": "solid", "strength_mg": 250, "unit": "tablet"},
                "Oral Tablet 500 mg": {"type": "solid", "strength_mg": 500, "unit": "tablet"}
            },
            "counseling": [
                "Oral suspension MUST be taken with food to enhance absorption.",
                "Do not crush tablets (extremely bitter taste); use suspension for children unable to swallow tablets whole.",
                "Store reconstituted suspension in the refrigerator and discard after 10 days."
            ]
        },
        "Cefpodoxime Proxetil (Vantin)": {
            "category": "Antibiotics",
            "sources": [
                {"title": "AAP Guideline: Acute Otitis Media", "url": "https://doi.org/10.1542/peds.2012-3488"},
                {"title": "DailyMed FDA Label: Cefpodoxime Proxetil", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=CEFPODOXIME"}
            ],
            "indications": {
                "Acute Otitis Media / Sinusitis / Pharyngitis (10 mg/kg/day Q12H)": {"dose_mg_kg_day": 10.0, "freq": 2, "max_single": 200.0, "max_daily": 400.0}
            },
            "forms": {
                "Oral Suspension 50 mg / 5 mL": {"type": "liquid", "conc_mg": 50, "conc_ml": 5},
                "Oral Suspension 100 mg / 5 mL": {"type": "liquid", "conc_mg": 100, "conc_ml": 5},
                "Oral Tablet 100 mg": {"type": "solid", "strength_mg": 100, "unit": "tablet"},
                "Oral Tablet 200 mg": {"type": "solid", "strength_mg": 200, "unit": "tablet"}
            },
            "counseling": [
                "Oral suspension may be taken with or without food; tablets should be taken with food to maximize absorption.",
                "Refrigerate suspension after mixing and discard after 14 days."
            ]
        },
        "Cefdinir (Omnicef)": {
            "category": "Antibiotics",
            "sources": [
                {"title": "AAP Guideline: Acute Otitis Media", "url": "https://doi.org/10.1542/peds.2012-3488"},
                {"title": "DailyMed FDA Label: Cefdinir", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=CEFDINIR"}
            ],
            "indications": {
                "Otitis Media / Sinusitis / Pharyngitis (Divided: 14 mg/kg/day Q12H)": {"dose_mg_kg_day": 14.0, "freq": 2, "max_single": 300.0, "max_daily": 600.0},
                "Pharyngitis / Uncomplicated Skin Infection (Once Daily: 14 mg/kg/day Q24H)": {"dose_mg_kg_day": 14.0, "freq": 1, "max_single": 600.0, "max_daily": 600.0}
            },
            "forms": {
                "Oral Suspension 125 mg / 5 mL": {"type": "liquid", "conc_mg": 125, "conc_ml": 5},
                "Oral Suspension 250 mg / 5 mL": {"type": "liquid", "conc_mg": 250, "conc_ml": 5},
                "Oral Capsule 300 mg": {"type": "solid", "strength_mg": 300, "unit": "capsule"}
            },
            "counseling": [
                "Separate by at least 2 hours from iron supplements or aluminum/magnesium antacids.",
                "Harmless reddish/rust-colored stools may occur if co-administered with iron-containing products.",
                "Store reconstituted suspension at room temperature (do not refrigerate); discard after 10 days."
            ]
        },
        "Cephalexin (Keflex)": {
            "category": "Antibiotics",
            "sources": [
                {"title": "IDSA Guideline: Skin and Soft Tissue Infections", "url": "https://doi.org/10.1093/cid/ciu296"},
                {"title": "DailyMed FDA Label: Cephalexin", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=CEPHALEXIN"}
            ],
            "indications": {
                "Mild-to-Moderate Skin / UTI (50 mg/kg/day Q8H)": {"dose_mg_kg_day": 50.0, "freq": 3, "max_single": 500.0, "max_daily": 2000.0},
                "Streptococcal Pharyngitis (40 mg/kg/day Q12H)": {"dose_mg_kg_day": 40.0, "freq": 2, "max_single": 500.0, "max_daily": 1000.0},
                "Severe Skin / Bone Infection (75 mg/kg/day Q8H)": {"dose_mg_kg_day": 75.0, "freq": 3, "max_single": 1000.0, "max_daily": 3000.0}
            },
            "forms": {
                "Oral Suspension 250 mg / 5 mL": {"type": "liquid", "conc_mg": 250, "conc_ml": 5},
                "Oral Suspension 125 mg / 5 mL": {"type": "liquid", "conc_mg": 125, "conc_ml": 5},
                "Oral Capsule 250 mg": {"type": "solid", "strength_mg": 250, "unit": "capsule"},
                "Oral Capsule 500 mg": {"type": "solid", "strength_mg": 500, "unit": "capsule"}
            },
            "counseling": [
                "Can be taken with or without food.",
                "Refrigerate suspension after reconstitution and discard after 14 days."
            ]
        },
        "Clarithromycin (Klacid / Biaxin)": {
            "category": "Antibiotics",
            "sources": [
                {"title": "PIDS/IDSA Guideline: Pediatric Community-Acquired Pneumonia", "url": "https://doi.org/10.1093/cid/cir531"},
                {"title": "DailyMed FDA Label: Clarithromycin", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=CLARITHROMYCIN"}
            ],
            "indications": {
                "Atypical Pneumonia / Pharyngitis / Otitis Media (15 mg/kg/day Q12H)": {"dose_mg_kg_day": 15.0, "freq": 2, "max_single": 500.0, "max_daily": 1000.0}
            },
            "forms": {
                "Oral Suspension 125 mg / 5 mL": {"type": "liquid", "conc_mg": 125, "conc_ml": 5},
                "Oral Suspension 250 mg / 5 mL": {"type": "liquid", "conc_mg": 250, "conc_ml": 5},
                "Oral Tablet 250 mg": {"type": "solid", "strength_mg": 250, "unit": "tablet"},
                "Oral Tablet 500 mg": {"type": "solid", "strength_mg": 500, "unit": "tablet"}
            },
            "counseling": [
                "Do NOT refrigerate reconstituted suspension (causes bitter taste and thickening); store at room temperature and use within 14 days.",
                "Potent CYP3A4 inhibitor — check for interactions with domperidone, statins, and carbamazepine."
            ]
        },
        "Azithromycin (Zithromax)": {
            "category": "Antibiotics",
            "sources": [
                {"title": "PIDS/IDSA Guideline: Pediatric Community-Acquired Pneumonia", "url": "https://doi.org/10.1093/cid/cir531"},
                {"title": "DailyMed FDA Label: Azithromycin", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=AZITHROMYCIN"}
            ],
            "indications": {
                "CAP / Pertussis — Day 1 Loading Dose (10 mg/kg Q24H)": {"dose_mg_kg_day": 10.0, "freq": 1, "max_single": 500.0, "max_daily": 500.0},
                "CAP / Pertussis — Days 2–5 Maintenance (5 mg/kg Q24H)": {"dose_mg_kg_day": 5.0, "freq": 1, "max_single": 250.0, "max_daily": 250.0},
                "Streptococcal Pharyngitis — 5-Day Regimen (12 mg/kg/day Q24H)": {"dose_mg_kg_day": 12.0, "freq": 1, "max_single": 500.0, "max_daily": 500.0},
                "Acute Otitis Media — 3-Day Regimen (10 mg/kg/day Q24H)": {"dose_mg_kg_day": 10.0, "freq": 1, "max_single": 500.0, "max_daily": 500.0}
            },
            "forms": {
                "Oral Suspension 200 mg / 5 mL": {"type": "liquid", "conc_mg": 200, "conc_ml": 5},
                "Oral Suspension 100 mg / 5 mL": {"type": "liquid", "conc_mg": 100, "conc_ml": 5},
                "Oral Tablet 250 mg": {"type": "solid", "strength_mg": 250, "unit": "tablet"},
                "Oral Tablet 500 mg": {"type": "solid", "strength_mg": 500, "unit": "tablet"}
            },
            "counseling": [
                "May be taken with or without food.",
                "Separate from aluminum/magnesium antacids by at least 2 hours.",
                "Store reconstituted suspension at room temperature (5°C to 30°C) and discard after 10 days."
            ]
        },
        "Erythromycin Ethylsuccinate (EES)": {
            "category": "Antibiotics",
            "sources": [
                {"title": "CDC Guideline: Pertussis Treatment & Prophylaxis", "url": "https://www.cdc.gov/pertussis/hcp/clinical-care/index.html"},
                {"title": "DailyMed FDA Label: Erythromycin Ethylsuccinate", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=ERYTHROMYCIN+ETHYLSUCCINATE"}
            ],
            "indications": {
                "Pertussis / Mild-to-Moderate Infections (40 mg/kg/day Q6H)": {"dose_mg_kg_day": 40.0, "freq": 4, "max_single": 500.0, "max_daily": 2000.0}
            },
            "forms": {
                "Oral Suspension 200 mg / 5 mL": {"type": "liquid", "conc_mg": 200, "conc_ml": 5},
                "Oral Suspension 400 mg / 5 mL": {"type": "liquid", "conc_mg": 400, "conc_ml": 5}
            },
            "counseling": [
                "May be taken with food or milk to decrease frequent GI cramping.",
                "Associated with infantile hypertrophic pyloric stenosis in neonates < 6 weeks old (azithromycin is preferred in neonates)."
            ]
        },
        "Clindamycin (Cleocin)": {
            "category": "Antibiotics",
            "sources": [
                {"title": "IDSA Guideline: MRSA Infections in Children", "url": "https://doi.org/10.1093/cid/ciq146"},
                {"title": "DailyMed FDA Label: Clindamycin Palmitate", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=CLINDAMYCIN"}
            ],
            "indications": {
                "Purulent Skin/Soft Tissue Infection — MRSA (30 mg/kg/day Q8H)": {"dose_mg_kg_day": 30.0, "freq": 3, "max_single": 600.0, "max_daily": 1800.0},
                "Severe Infection / Pneumonia / Osteomyelitis (40 mg/kg/day Q8H)": {"dose_mg_kg_day": 40.0, "freq": 3, "max_single": 600.0, "max_daily": 1800.0},
                "Odontogenic / Dental Infection (20 mg/kg/day Q8H)": {"dose_mg_kg_day": 20.0, "freq": 3, "max_single": 450.0, "max_daily": 1350.0}
            },
            "forms": {
                "Oral Solution 75 mg / 5 mL": {"type": "liquid", "conc_mg": 75, "conc_ml": 5},
                "Oral Capsule 150 mg": {"type": "solid", "strength_mg": 150, "unit": "capsule"},
                "Oral Capsule 300 mg": {"type": "solid", "strength_mg": 300, "unit": "capsule"}
            },
            "counseling": [
                "Administer capsules with a full glass of water and remain upright for 30 minutes to prevent esophageal ulceration.",
                "Do NOT refrigerate reconstituted oral solution (causes thickening/precipitation); store at room temperature for up to 14 days."
            ]
        },
        "Sulfamethoxazole-Trimethoprim (Bactrim)": {
            "category": "Antibiotics",
            "sources": [
                {"title": "IDSA Guideline: MRSA Skin & Soft Tissue Infections", "url": "https://doi.org/10.1093/cid/ciq146"},
                {"title": "DailyMed FDA Label: Sulfamethoxazole and Trimethoprim", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=SULFAMETHOXAZOLE+AND+TRIMETHOPRIM"}
            ],
            "indications": {
                "UTI / Acute Otitis Media (8 mg/kg/day TMP component Q12H)": {"dose_mg_kg_day": 8.0, "freq": 2, "max_single": 160.0, "max_daily": 320.0, "smx_ratio": 5.0},
                "Purulent MRSA Skin Infection (10 mg/kg/day TMP component Q12H)": {"dose_mg_kg_day": 10.0, "freq": 2, "max_single": 160.0, "max_daily": 320.0, "smx_ratio": 5.0}
            },
            "forms": {
                "Oral Suspension (40 mg TMP + 200 mg SMX per 5 mL)": {"type": "liquid", "conc_mg": 40, "conc_ml": 5},
                "Single Strength Tablet (80 mg TMP + 400 mg SMX)": {"type": "solid", "strength_mg": 80, "unit": "tablet"},
                "Double Strength Tablet (160 mg TMP + 800 mg SMX)": {"type": "solid", "strength_mg": 160, "unit": "tablet"}
            },
            "counseling": [
                "Contraindicated in infants < 2 months of age (risk of kernicterus).",
                "Dosing is calculated on the Trimethoprim (TMP) component (1:5 ratio with Sulfamethoxazole).",
                "Maintain adequate fluid intake to prevent crystalluria; use sunscreen due to photosensitivity."
            ]
        },
        "Metronidazole (Flagyl)": {
            "category": "Antibiotics",
            "sources": [
                {"title": "IDSA/SHEA Guideline: Clostridioides difficile Infection", "url": "https://doi.org/10.1093/cid/cix1085"},
                {"title": "DailyMed FDA Label: Metronidazole", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=METRONIDAZOLE"}
            ],
            "indications": {
                "Giardiasis (15 mg/kg/day Divided Q8H for 5–7 Days)": {"dose_mg_kg_day": 15.0, "freq": 3, "max_single": 250.0, "max_daily": 750.0},
                "Anaerobic Infection / Non-Severe C. difficile (30 mg/kg/day Divided Q6H)": {"dose_mg_kg_day": 30.0, "freq": 4, "max_single": 500.0, "max_daily": 2000.0},
                "Intestinal Amebiasis (40 mg/kg/day Divided Q8H for 7–10 Days)": {"dose_mg_kg_day": 40.0, "freq": 3, "max_single": 750.0, "max_daily": 2250.0}
            },
            "forms": {
                "Oral Suspension (Benzoate) 125 mg / 5 mL": {"type": "liquid", "conc_mg": 125, "conc_ml": 5},
                "Oral Suspension (Benzoate) 200 mg / 5 mL": {"type": "liquid", "conc_mg": 200, "conc_ml": 5},
                "Oral Tablet 250 mg": {"type": "solid", "strength_mg": 250, "unit": "tablet"},
                "Oral Tablet 500 mg": {"type": "solid", "strength_mg": 500, "unit": "tablet"}
            },
            "counseling": [
                "Take with food to reduce gastrointestinal upset and metallic taste.",
                "May harmlessly darken urine (reddish-brown discoloration)."
            ]
        },
        "Nitrofurantoin (Macrodantin / Uvamin)": {
            "category": "Antibiotics",
            "sources": [
                {"title": "DailyMed FDA Label: Nitrofurantoin Oral Suspension", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=NITROFURANTOIN"}
            ],
            "indications": {
                "Uncomplicated Lower UTI / Cystitis (6 mg/kg/day Divided Q6H)": {"dose_mg_kg_day": 6.0, "freq": 4, "max_single": 100.0, "max_daily": 400.0},
                "UTI Prophylaxis (2 mg/kg/day Once Daily at Bedtime)": {"dose_mg_kg_day": 2.0, "freq": 1, "max_single": 100.0, "max_daily": 100.0}
            },
            "forms": {
                "Oral Suspension 25 mg / 5 mL": {"type": "liquid", "conc_mg": 25, "conc_ml": 5},
                "Macrocrystal Capsule 50 mg": {"type": "solid", "strength_mg": 50, "unit": "capsule"},
                "Macrocrystal Capsule 100 mg": {"type": "solid", "strength_mg": 100, "unit": "capsule"}
            },
            "counseling": [
                "Administer with food or milk to improve absorption and decrease nausea.",
                "Contraindicated in infants < 1 month old and in patients with G6PD deficiency (hemolytic anemia risk).",
                "Do NOT use for febrile UTI or pyelonephritis (does not achieve therapeutic renal parenchymal concentrations)."
            ]
        },

        # =====================================================================
        # CATEGORY 2: GASTROINTESTINAL
        # =====================================================================
        "Domperidone": {
            "category": "Gastrointestinal",
            "sources": [
                {"title": "EMA Article 31 Referral: Domperidone Pediatric Safety Restrictions", "url": "https://www.ema.europa.eu/en/documents/referral/domperidone-article-31-referral-annex-iii_en.pdf"},
                {"title": "Medicines.org.uk (SmPC): Domperidone 1 mg/mL Oral Suspension", "url": "https://www.medicines.org.uk/emc/search?q=domperidone"}
            ],
            "indications": {
                "Relief of Nausea & Vomiting (EMA Guideline: 0.25 mg/kg TID)": {"dose_mg_kg_dose": 0.25, "freq": 3, "max_single": 10.0, "max_daily": 30.0}
            },
            "forms": {
                "Oral Suspension 1 mg / 1 mL (5 mg / 5 mL)": {"type": "liquid", "conc_mg": 1, "conc_ml": 1},
                "Oral Tablet 10 mg": {"type": "solid", "strength_mg": 10, "unit": "tablet"}
            },
            "counseling": [
                "Administer 15 to 30 minutes before meals/feeds.",
                "EMA/MHRA Safety Restriction: Use the lowest effective dose for the shortest duration (maximum 7 days).",
                "🛑 Contraindicated with potent CYP3A4 inhibitors (e.g., clarithromycin, ketoconazole) or QTc-prolonging drugs due to risk of ventricular arrhythmia."
            ]
        },
        "Metoclopramide (Reglan / Plasil)": {
            "category": "Gastrointestinal",
            "sources": [
                {"title": "EMA CHMP Assessment: Metoclopramide Pediatric Dose Restrictions", "url": "https://www.ema.europa.eu/en/medicines/human/referrals/metoclopramide-containing-medicines"},
                {"title": "DailyMed FDA Label: Metoclopramide", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=METOCLOPRAMIDE"}
            ],
            "indications": {
                "Second-Line Post-Op / Chemo Nausea (0.15 mg/kg/dose TID)": {"dose_mg_kg_dose": 0.15, "freq": 3, "max_single": 10.0, "max_daily": 30.0},
                "Conservative Pediatric Regimen (0.1 mg/kg/dose TID)": {"dose_mg_kg_dose": 0.1, "freq": 3, "max_single": 10.0, "max_daily": 30.0}
            },
            "forms": {
                "Oral Solution 5 mg / 5 mL (1 mg / mL)": {"type": "liquid", "conc_mg": 5, "conc_ml": 5},
                "Oral Tablet 10 mg": {"type": "solid", "strength_mg": 10, "unit": "tablet"}
            },
            "counseling": [
                "🛑 Contraindicated in children < 1 year of age due to high risk of extrapyramidal disorders (acute dystonia, oculogyric crisis).",
                "Maximum daily dose must not exceed 0.5 mg/kg/day; limit treatment duration to a maximum of 5 days."
            ]
        },
        "Ondansetron (Zofran)": {
            "category": "Gastrointestinal",
            "sources": [
                {"title": "ESPGHAN/ESPID Guideline: Acute Gastroenteritis in Children", "url": "https://doi.org/10.1097/MPG.0000000000000322"},
                {"title": "DailyMed FDA Label: Ondansetron", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=ONDANSETRON"}
            ],
            "indications": {
                "Acute Gastroenteritis Vomiting (Weight-Banded Single/Q8H Protocol)": {
                    "type": "weight_bands",
                    "bands": [
                        {"min_wt": 8.0, "max_wt": 15.0, "dose_mg": 2.0},
                        {"min_wt": 15.0, "max_wt": 30.0, "dose_mg": 4.0},
                        {"min_wt": 30.0, "max_wt": 999.0, "dose_mg": 8.0}
                    ],
                    "fallback_mg_kg": 0.15,
                    "freq": 3,
                    "max_single": 8.0,
                    "max_daily": 24.0
                },
                "Exact Weight-Based Protocol (0.15 mg/kg/dose Q8H)": {"dose_mg_kg_dose": 0.15, "freq": 3, "max_single": 8.0, "max_daily": 24.0}
            },
            "forms": {
                "Oral Solution 4 mg / 5 mL": {"type": "liquid", "conc_mg": 4, "conc_ml": 5},
                "Orally Disintegrating Tablet (ODT) 4 mg": {"type": "solid", "strength_mg": 4, "unit": "tablet"},
                "Orally Disintegrating Tablet (ODT) 8 mg": {"type": "solid", "strength_mg": 8, "unit": "tablet"}
            },
            "counseling": [
                "For acute gastroenteritis, a single oral dose is usually sufficient to facilitate oral rehydration therapy (ORT).",
                "Begin oral rehydration fluids 15–30 minutes after administering ondansetron."
            ]
        },
        "Omeprazole (Losec / Prilosec)": {
            "category": "Gastrointestinal",
            "sources": [
                {"title": "NASPGHAN/ESPGHAN Pediatric GERD Clinical Practice Guideline", "url": "https://doi.org/10.1097/MPG.0000000000001889"},
                {"title": "DailyMed FDA Label: Omeprazole Delayed-Release", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=OMEPRAZOLE"}
            ],
            "indications": {
                "Pediatric GERD / Erosive Esophagitis (Weight-Banded Once Daily)": {
                    "type": "weight_bands",
                    "bands": [
                        {"min_wt": 5.0, "max_wt": 10.0, "dose_mg": 5.0},
                        {"min_wt": 10.0, "max_wt": 20.0, "dose_mg": 10.0},
                        {"min_wt": 20.0, "max_wt": 999.0, "dose_mg": 20.0}
                    ],
                    "fallback_mg_kg": 1.0,
                    "freq": 1,
                    "max_single": 40.0,
                    "max_daily": 40.0
                },
                "Exact Weight-Based GERD Protocol (1 mg/kg/day Q24H)": {"dose_mg_kg_day": 1.0, "freq": 1, "max_single": 40.0, "max_daily": 40.0}
            },
            "forms": {
                "Oral Suspension 2 mg / 1 mL (10 mg / 5 mL)": {"type": "liquid", "conc_mg": 2, "conc_ml": 1},
                "Delayed-Release Capsule 10 mg": {"type": "solid", "strength_mg": 10, "unit": "capsule"},
                "Delayed-Release Capsule 20 mg": {"type": "solid", "strength_mg": 20, "unit": "capsule"}
            },
            "counseling": [
                "Administer 30 minutes prior to the morning meal for optimal proton pump inhibition.",
                "Do not crush or chew enteric-coated granules; capsules may be opened and sprinkled on 1 tablespoon of applesauce."
            ]
        },
        "Lansoprazole (Prevacid / Lanzor)": {
            "category": "Gastrointestinal",
            "sources": [
                {"title": "NASPGHAN/ESPGHAN Pediatric GERD Clinical Practice Guideline", "url": "https://doi.org/10.1097/MPG.0000000000001889"},
                {"title": "DailyMed FDA Label: Lansoprazole", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=LANSOPRAZOLE"}
            ],
            "indications": {
                "Pediatric GERD / Erosive Esophagitis (Weight-Banded Once Daily)": {
                    "type": "weight_bands",
                    "bands": [
                        {"min_wt": 5.0, "max_wt": 30.0, "dose_mg": 15.0},
                        {"min_wt": 30.0, "max_wt": 999.0, "dose_mg": 30.0}
                    ],
                    "fallback_mg_kg": 1.4,
                    "freq": 1,
                    "max_single": 30.0,
                    "max_daily": 30.0
                }
            },
            "forms": {
                "Orally Disintegrating Tablet (Fastab) 15 mg": {"type": "solid", "strength_mg": 15, "unit": "tablet"},
                "Orally Disintegrating Tablet (Fastab) 30 mg": {"type": "solid", "strength_mg": 30, "unit": "tablet"},
                "Compounded Oral Suspension 3 mg / 1 mL": {"type": "liquid", "conc_mg": 3, "conc_ml": 1}
            },
            "counseling": [
                "Administer 30 minutes before the morning meal.",
                "ODT may be placed on the tongue to disintegrate or dispersed in a small amount of water and administered via oral syringe."
            ]
        },
        "Famotidine (Pepcid / Famodar)": {
            "category": "Gastrointestinal",
            "sources": [
                {"title": "NASPGHAN/ESPGHAN Pediatric GERD Clinical Practice Guideline", "url": "https://doi.org/10.1097/MPG.0000000000001889"},
                {"title": "DailyMed FDA Label: Famotidine Oral Suspension", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=FAMOTIDINE"}
            ],
            "indications": {
                "Symptomatic GERD / Esophagitis (1 mg/kg/day Divided Q12H)": {"dose_mg_kg_day": 1.0, "freq": 2, "max_single": 20.0, "max_daily": 40.0},
                "Peptic Ulcer Disease (0.5 mg/kg/day Q24H at Bedtime)": {"dose_mg_kg_day": 0.5, "freq": 1, "max_single": 40.0, "max_daily": 40.0}
            },
            "forms": {
                "Oral Suspension 40 mg / 5 mL (8 mg / mL)": {"type": "liquid", "conc_mg": 40, "conc_ml": 5},
                "Oral Tablet 10 mg": {"type": "solid", "strength_mg": 10, "unit": "tablet"},
                "Oral Tablet 20 mg": {"type": "solid", "strength_mg": 20, "unit": "tablet"},
                "Oral Tablet 40 mg": {"type": "solid", "strength_mg": 40, "unit": "tablet"}
            },
            "counseling": [
                "Shake reconstituted oral suspension vigorously before each dose; discard unused suspension after 30 days.",
                "Tachyphylaxis (tolerance to acid suppression) can develop within 2–6 weeks of continuous H2-receptor antagonist use."
            ]
        },
        "Lactulose (Duphalac)": {
            "category": "Gastrointestinal",
            "sources": [
                {"title": "ESPGHAN/NASPGHAN Guideline: Functional Constipation in Children", "url": "https://doi.org/10.1097/MPG.0000000000000266"},
                {"title": "Medicines.org.uk (SmPC): Lactulose 3.3g/5mL Oral Solution", "url": "https://www.medicines.org.uk/emc/search?q=lactulose"}
            ],
            "indications": {
                "Pediatric Functional Constipation (1000 mg/kg/day [~1.5 mL/kg/day] Divided BID)": {"dose_mg_kg_day": 1000.0, "freq": 2, "max_single": 20000.0, "max_daily": 40000.0}
            },
            "forms": {
                "Oral Solution 3,335 mg / 5 mL (667 mg / mL)": {"type": "liquid", "conc_mg": 3335, "conc_ml": 5}
            },
            "counseling": [
                "May be mixed with water, fruit juice, or milk to improve palatability; ensure adequate daily water intake.",
                "Takes 24 to 48 hours to produce a normal bowel movement; abdominal bloating/flatulence is common initially."
            ]
        },
        "Simethicone (Infacol / Mylicon)": {
            "category": "Gastrointestinal",
            "sources": [
                {"title": "DailyMed FDA Label: Simethicone Infant Drops", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=SIMETHICONE"}
            ],
            "indications": {
                "Infantile Colic / Functional Gas Relief (Auto Weight-Adjusted QID)": {
                    "type": "weight_bands",
                    "bands": [
                        {"min_wt": 0.5, "max_wt": 10.9, "dose_mg": 20.0},
                        {"min_wt": 11.0, "max_wt": 999.0, "dose_mg": 40.0}
                    ],
                    "fallback_mg_kg": 2.0,
                    "freq": 4,
                    "max_single": 125.0,
                    "max_daily": 500.0
                }
            },
            "forms": {
                "Oral Drops 40 mg / 0.6 mL (66.7 mg / mL)": {"type": "liquid", "conc_mg": 40, "conc_ml": 0.6},
                "Oral Suspension 40 mg / 1 mL": {"type": "liquid", "conc_mg": 40, "conc_ml": 1},
                "Chewable Tablet 80 mg": {"type": "solid", "strength_mg": 80, "unit": "tablet"}
            },
            "counseling": [
                "Administer after meals and at bedtime (can be mixed with 30 mL of cool water or infant formula).",
                "Not absorbed systemically; acts locally in the gut lumen to coalesce gas bubbles."
            ]
        },

        # =====================================================================
        # CATEGORY 3: ALLERGY & ANTIHISTAMINES
        # =====================================================================
        "Cetirizine (Zyrtec)": {
            "category": "Allergy & Antihistamines",
            "sources": [
                {"title": "AAAAI/ACAAI Practice Parameter: Allergic Rhinitis", "url": "https://doi.org/10.1016/j.jaci.2020.07.007"},
                {"title": "DailyMed FDA Label: Cetirizine Hydrochloride", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=CETIRIZINE"}
            ],
            "indications": {
                "Allergic Rhinitis / Urticaria (Auto Age-Adjusted Dosing)": {
                    "type": "age_bands",
                    "bands": [
                        {"min_mo": 6.0, "max_mo": 24.0, "dose_mg": 2.5, "freq": 1, "note": "Age 6–23 months: 2.5 mg once daily"},
                        {"min_mo": 24.0, "max_mo": 72.0, "dose_mg": 2.5, "freq": 1, "note": "Age 2–5 years: 2.5 mg once daily (may increase to 5 mg/day)"},
                        {"min_mo": 72.0, "max_mo": 9999.0, "dose_mg": 10.0, "freq": 1, "note": "Age ≥ 6 years: 5–10 mg once daily"}
                    ]
                }
            },
            "forms": {
                "Oral Syrup 5 mg / 5 mL (1 mg / mL)": {"type": "liquid", "conc_mg": 5, "conc_ml": 5},
                "Oral Drops 10 mg / 1 mL (0.5 mg / drop)": {"type": "liquid", "conc_mg": 10, "conc_ml": 1},
                "Chewable Tablet 5 mg": {"type": "solid", "strength_mg": 5, "unit": "tablet"},
                "Oral Tablet 10 mg": {"type": "solid", "strength_mg": 10, "unit": "tablet"}
            },
            "counseling": [
                "Second-generation antihistamine; may still cause mild drowsiness in a subset of patients (administer in the evening if sedation occurs).",
                "Can be administered with or without food."
            ]
        },
        "Levocetirizine (Xyzal)": {
            "category": "Allergy & Antihistamines",
            "sources": [
                {"title": "DailyMed FDA Label: Levocetirizine Dihydrochloride", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=LEVOCETIRIZINE"}
            ],
            "indications": {
                "Allergic Rhinitis / Urticaria (Auto Age-Adjusted Evening Dosing)": {
                    "type": "age_bands",
                    "bands": [
                        {"min_mo": 6.0, "max_mo": 72.0, "dose_mg": 1.25, "freq": 1, "note": "Age 6 months – 5 years: 1.25 mg (2.5 mL) once daily in the evening"},
                        {"min_mo": 72.0, "max_mo": 144.0, "dose_mg": 2.5, "freq": 1, "note": "Age 6–11 years: 2.5 mg once daily in the evening"},
                        {"min_mo": 144.0, "max_mo": 9999.0, "dose_mg": 5.0, "freq": 1, "note": "Age ≥ 12 years: 5 mg once daily in the evening"}
                    ]
                }
            },
            "forms": {
                "Oral Solution 2.5 mg / 5 mL (0.5 mg / mL)": {"type": "liquid", "conc_mg": 2.5, "conc_ml": 5},
                "Oral Tablet 5 mg": {"type": "solid", "strength_mg": 5, "unit": "tablet"}
            },
            "counseling": [
                "Administer in the evening.",
                "Do not exceed recommended pediatric age-specific doses (higher doses increase somnolence without added efficacy)."
            ]
        },
        "Desloratadine (Aerius / Clarinex)": {
            "category": "Allergy & Antihistamines",
            "sources": [
                {"title": "DailyMed FDA Label: Desloratadine Oral Solution", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=DESLORATADINE"},
                {"title": "EMA EPAR Product Information: Aerius (Desloratadine)", "url": "https://www.ema.europa.eu/en/medicines/human/EPAR/aerius"}
            ],
            "indications": {
                "Allergic Rhinitis / Chronic Urticaria (Auto Age-Adjusted Dosing)": {
                    "type": "age_bands",
                    "bands": [
                        {"min_mo": 6.0, "max_mo": 12.0, "dose_mg": 1.0, "freq": 1, "note": "Age 6–11 months: 1 mg (2 mL) once daily"},
                        {"min_mo": 12.0, "max_mo": 72.0, "dose_mg": 1.25, "freq": 1, "note": "Age 1–5 years: 1.25 mg (2.5 mL) once daily"},
                        {"min_mo": 72.0, "max_mo": 144.0, "dose_mg": 2.5, "freq": 1, "note": "Age 6–11 years: 2.5 mg (5 mL) once daily"},
                        {"min_mo": 144.0, "max_mo": 9999.0, "dose_mg": 5.0, "freq": 1, "note": "Age ≥ 12 years: 5 mg once daily"}
                    ]
                }
            },
            "forms": {
                "Oral Syrup / Solution 2.5 mg / 5 mL (0.5 mg / mL)": {"type": "liquid", "conc_mg": 2.5, "conc_ml": 5},
                "Oral Tablet 5 mg": {"type": "solid", "strength_mg": 5, "unit": "tablet"}
            },
            "counseling": [
                "Non-sedating, long-acting active metabolite of loratadine.",
                "May be taken with or without food."
            ]
        },
        "Loratadine (Claritin)": {
            "category": "Allergy & Antihistamines",
            "sources": [
                {"title": "DailyMed FDA Label: Loratadine Syrup", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=LORATADINE"}
            ],
            "indications": {
                "Allergic Rhinitis / Urticaria (Auto Age-Adjusted Dosing)": {
                    "type": "age_bands",
                    "bands": [
                        {"min_mo": 24.0, "max_mo": 72.0, "dose_mg": 5.0, "freq": 1, "note": "Age 2–5 years: 5 mg once daily"},
                        {"min_mo": 72.0, "max_mo": 9999.0, "dose_mg": 10.0, "freq": 1, "note": "Age ≥ 6 years: 10 mg once daily"}
                    ]
                }
            },
            "forms": {
                "Oral Syrup 5 mg / 5 mL (1 mg / mL)": {"type": "liquid", "conc_mg": 5, "conc_ml": 5},
                "Chewable Tablet 5 mg": {"type": "solid", "strength_mg": 5, "unit": "tablet"},
                "Oral Tablet 10 mg": {"type": "solid", "strength_mg": 10, "unit": "tablet"}
            },
            "counseling": [
                "Non-sedating second-generation antihistamine.",
                "Not recommended in children under 2 years of age."
            ]
        },
        "Fexofenadine (Telfast / Allegra)": {
            "category": "Allergy & Antihistamines",
            "sources": [
                {"title": "DailyMed FDA Label: Fexofenadine Children's Suspension", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=FEXOFENADINE"}
            ],
            "indications": {
                "Allergic Rhinitis / Urticaria (Auto Age-Adjusted Dosing)": {
                    "type": "age_bands",
                    "bands": [
                        {"min_mo": 6.0, "max_mo": 24.0, "dose_mg": 15.0, "freq": 2, "note": "Age 6–23 months: 15 mg (2.5 mL) twice daily"},
                        {"min_mo": 24.0, "max_mo": 144.0, "dose_mg": 30.0, "freq": 2, "note": "Age 2–11 years: 30 mg (5 mL) twice daily"},
                        {"min_mo": 144.0, "max_mo": 9999.0, "dose_mg": 60.0, "freq": 2, "note": "Age ≥ 12 years: 60 mg twice daily (or 180 mg once daily)"}
                    ]
                }
            },
            "forms": {
                "Oral Suspension 30 mg / 5 mL (6 mg / mL)": {"type": "liquid", "conc_mg": 30, "conc_ml": 5},
                "Oral Tablet 60 mg": {"type": "solid", "strength_mg": 60, "unit": "tablet"},
                "Oral Tablet 120 mg": {"type": "solid", "strength_mg": 120, "unit": "tablet"},
                "Oral Tablet 180 mg": {"type": "solid", "strength_mg": 180, "unit": "tablet"}
            },
            "counseling": [
                "Administer with water only. Avoid apple, orange, or grapefruit juice within 4 hours (inhibits OATP1A2 transporter and reduces absorption by ~40%).",
                "Separate from aluminum/magnesium antacids by at least 2 hours."
            ]
        },
        "Ketotifen (Zaditen)": {
            "category": "Allergy & Antihistamines",
            "sources": [
                {"title": "Medicines.org.uk (SmPC): Zaditen 1 mg/5 mL Elixir & Tablets", "url": "https://www.medicines.org.uk/emc/search?q=ketotifen"}
            ],
            "indications": {
                "Allergic Conditions / Asthma Prophylaxis (Auto Age & Weight Adjusted)": {
                    "type": "ketotifen_hybrid"
                }
            },
            "forms": {
                "Oral Syrup 1 mg / 5 mL (0.2 mg / mL)": {"type": "liquid", "conc_mg": 1, "conc_ml": 5},
                "Oral Tablet 1 mg": {"type": "solid", "strength_mg": 1, "unit": "tablet"}
            },
            "counseling": [
                "Take with food.",
                "For children 6 months to 3 years: dosed at 0.05 mg/kg twice daily. For children > 3 years: 1 mg (5 mL) twice daily.",
                "Not effective for acute asthma attacks; requires several weeks of continuous therapy for maximal prophylactic effect."
            ]
        },
        "Chlorpheniramine Maleate (Allerfin / Piriton)": {
            "category": "Allergy & Antihistamines",
            "sources": [
                {"title": "Medicines.org.uk (SmPC): Piriton (Chlorphenamine) Syrup", "url": "https://www.medicines.org.uk/emc/search?q=chlorphenamine"},
                {"title": "DailyMed FDA Label: Chlorpheniramine Maleate", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=CHLORPHENIRAMINE"}
            ],
            "indications": {
                "Symptomatic Allergy / Urticaria (Auto Age-Banded Q6H)": {
                    "type": "age_bands",
                    "bands": [
                        {"min_mo": 12.0, "max_mo": 24.0, "dose_mg": 1.0, "freq": 2, "note": "Age 1–2 years: 1 mg (2.5 mL) twice daily (max 2 mg/day)"},
                        {"min_mo": 24.0, "max_mo": 72.0, "dose_mg": 1.0, "freq": 4, "note": "Age 2–5 years: 1 mg (2.5 mL) every 6 hours (max 6 mg/day)"},
                        {"min_mo": 72.0, "max_mo": 144.0, "dose_mg": 2.0, "freq": 4, "note": "Age 6–11 years: 2 mg (5 mL) every 6 hours (max 12 mg/day)"},
                        {"min_mo": 144.0, "max_mo": 9999.0, "dose_mg": 4.0, "freq": 4, "note": "Age ≥ 12 years: 4 mg every 6 hours (max 24 mg/day)"}
                    ]
                },
                "Weight-Based Calculation (0.35 mg/kg/day Divided Q6H)": {"dose_mg_kg_day": 0.35, "freq": 4, "max_single": 4.0, "max_daily": 16.0}
            },
            "forms": {
                "Oral Syrup 2 mg / 5 mL": {"type": "liquid", "conc_mg": 2, "conc_ml": 5},
                "Oral Tablet 4 mg": {"type": "solid", "strength_mg": 4, "unit": "tablet"}
            },
            "counseling": [
                "First-generation sedating antihistamine; causes drowsiness or paradoxical CNS excitation in young children.",
                "Not recommended in infants under 1 year of age."
            ]
        },
        "Hydroxyzine (Atarax)": {
            "category": "Allergy & Antihistamines",
            "sources": [
                {"title": "EMA PRAC Referral: Hydroxyzine Maximum Dose & QTc Restrictions", "url": "https://www.ema.europa.eu/en/medicines/human/referrals/hydroxyzine-containing-medicinal-products"},
                {"title": "DailyMed FDA Label: Hydroxyzine Hydrochloride", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=HYDROXYZINE"}
            ],
            "indications": {
                "Pruritus / Chronic Urticaria (2 mg/kg/day Divided Q8H)": {"dose_mg_kg_day": 2.0, "freq": 3, "max_single": 25.0, "max_daily": 100.0}
            },
            "forms": {
                "Oral Syrup 10 mg / 5 mL (2 mg / mL)": {"type": "liquid", "conc_mg": 10, "conc_ml": 5},
                "Oral Tablet 10 mg": {"type": "solid", "strength_mg": 10, "unit": "tablet"},
                "Oral Tablet 25 mg": {"type": "solid", "strength_mg": 25, "unit": "tablet"}
            },
            "counseling": [
                "EMA Safety Restriction: In children up to 40 kg, maximum daily dose is 2 mg/kg/day; in children > 40 kg, maximum daily dose is 100 mg/day due to QTc prolongation risk.",
                "Causes significant sedation; administer largest dose at bedtime when treating nocturnal pruritus."
            ]
        },
        "Diphenhydramine (Benadryl)": {
            "category": "Allergy & Antihistamines",
            "sources": [
                {"title": "DailyMed FDA Label: Diphenhydramine Hydrochloride", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=DIPHENHYDRAMINE"}
            ],
            "indications": {
                "Acute Allergic Reaction / Urticaria (1.25 mg/kg/dose Q6H)": {"dose_mg_kg_dose": 1.25, "freq": 4, "max_single": 50.0, "max_daily": 300.0}
            },
            "forms": {
                "Oral Liquid 12.5 mg / 5 mL": {"type": "liquid", "conc_mg": 12.5, "conc_ml": 5},
                "Chewable Tablet 12.5 mg": {"type": "solid", "strength_mg": 12.5, "unit": "tablet"},
                "Oral Capsule 25 mg": {"type": "solid", "strength_mg": 25, "unit": "capsule"}
            },
            "counseling": [
                "🛑 Contraindicated in children < 2 years (risk of respiratory depression and paradoxical CNS excitation) unless directed under emergency anaphylaxis protocols.",
                "Causes marked sedation and anticholinergic effects."
            ]
        },

        # =====================================================================
        # CATEGORY 4: ANALGESICS & ANTIPYRETICS
        # =====================================================================
        "Ibuprofen": {
            "category": "Analgesics & Antipyretics",
            "sources": [
                {"title": "AAP Clinical Report: Fever and Antipyretic Use in Children", "url": "https://doi.org/10.1542/peds.2010-3852"},
                {"title": "DailyMed FDA Label: Children's Ibuprofen", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=IBUPROFEN"}
            ],
            "indications": {
                "Fever / Mild-to-Moderate Pain (10 mg/kg/dose Q8H, TID)": {"dose_mg_kg_dose": 10.0, "freq": 3, "max_single": 400.0, "max_daily": 1600.0},
                "Fever / Pain (Q6H Max Frequency — 40 mg/kg/day)": {"dose_mg_kg_dose": 10.0, "freq": 4, "max_single": 400.0, "max_daily": 2400.0}
            },
            "forms": {
                "Children's Oral Suspension 100 mg / 5 mL (20 mg/mL)": {"type": "liquid", "conc_mg": 100, "conc_ml": 5},
                "Infant Oral Drops 50 mg / 1.25 mL (40 mg/mL)": {"type": "liquid", "conc_mg": 50, "conc_ml": 1.25},
                "Chewable Tablet 100 mg": {"type": "solid", "strength_mg": 100, "unit": "tablet"},
                "Oral Tablet 200 mg": {"type": "solid", "strength_mg": 200, "unit": "tablet"},
                "Oral Tablet 400 mg": {"type": "solid", "strength_mg": 400, "unit": "tablet"}
            },
            "counseling": [
                "Avoid in infants < 6 months of age or in dehydrated patients (risk of acute kidney injury).",
                "Administer with food or milk to reduce gastrointestinal irritation.",
                "Verify concentration carefully: Infant Drops (40 mg/mL) are twice as concentrated as Children's Suspension (20 mg/mL)."
            ]
        },
        "Acetaminophen (Paracetamol)": {
            "category": "Analgesics & Antipyretics",
            "sources": [
                {"title": "AAP Clinical Report: Fever and Antipyretic Use in Children", "url": "https://doi.org/10.1542/peds.2010-3852"},
                {"title": "DailyMed FDA Label: Children's Acetaminophen", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=ACETAMINOPHEN"}
            ],
            "indications": {
                "Fever / Pain Management (15 mg/kg/dose Q6H — 60 mg/kg/day)": {"dose_mg_kg_dose": 15.0, "freq": 4, "max_single": 1000.0, "max_daily": 4000.0},
                "Fever / Pain (Conservative 10 mg/kg/dose Q6H)": {"dose_mg_kg_dose": 10.0, "freq": 4, "max_single": 1000.0, "max_daily": 4000.0}
            },
            "forms": {
                "Oral Suspension 160 mg / 5 mL (32 mg/mL)": {"type": "liquid", "conc_mg": 160, "conc_ml": 5},
                "Oral Suspension 120 mg / 5 mL (24 mg/mL)": {"type": "liquid", "conc_mg": 120, "conc_ml": 5},
                "Oral Suspension 250 mg / 5 mL (50 mg/mL Forte)": {"type": "liquid", "conc_mg": 250, "conc_ml": 5},
                "Infant Drops 100 mg / 1 mL": {"type": "liquid", "conc_mg": 100, "conc_ml": 1},
                "Rectal Suppository 125 mg": {"type": "solid", "strength_mg": 125, "unit": "suppository"},
                "Rectal Suppository 250 mg": {"type": "solid", "strength_mg": 250, "unit": "suppository"},
                "Oral Tablet 500 mg": {"type": "solid", "strength_mg": 500, "unit": "tablet"}
            },
            "counseling": [
                "Maximum pediatric daily dose must not exceed 75 mg/kg/day (or 4,000 mg/day, whichever is less) across all products.",
                "Check all co-administered cough/cold syrups to prevent accidental hepatotoxic overdose."
            ]
        },
        "Diclofenac (Cataflam / Voltaren)": {
            "category": "Analgesics & Antipyretics",
            "sources": [
                {"title": "Medicines.org.uk (SmPC): Diclofenac Pediatric Dosing", "url": "https://www.medicines.org.uk/emc/search?q=diclofenac"}
            ],
            "indications": {
                "Acute Pain / Post-Operative Inflammation (Age ≥ 1 yr: 1 mg/kg/dose TID)": {"dose_mg_kg_dose": 1.0, "freq": 3, "max_single": 50.0, "max_daily": 150.0}
            },
            "forms": {
                "Oral Drops (Cataflam) 15 mg / 1 mL (0.5 mg / drop)": {"type": "liquid", "conc_mg": 15, "conc_ml": 1},
                "Rectal Suppository 12.5 mg": {"type": "solid", "strength_mg": 12.5, "unit": "suppository"},
                "Rectal Suppository 25 mg": {"type": "solid", "strength_mg": 25, "unit": "suppository"},
                "Oral Tablet 25 mg": {"type": "solid", "strength_mg": 25, "unit": "tablet"},
                "Oral Tablet 50 mg": {"type": "solid", "strength_mg": 50, "unit": "tablet"}
            },
            "counseling": [
                "Not recommended in infants under 1 year of age.",
                "Administer with food; avoid concurrent use with Ibuprofen or systemic corticosteroids (severe GI ulceration and renal toxicity risk)."
            ]
        },

        # =====================================================================
        # CATEGORY 5: CORTICOSTEROIDS
        # =====================================================================
        "Prednisolone": {
            "category": "Corticosteroids",
            "sources": [
                {"title": "GINA Global Strategy for Asthma Management (Pediatric Exacerbations)", "url": "https://ginasthma.org/reports/"},
                {"title": "DailyMed FDA Label: Prednisolone Oral Solution", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=PREDNISOLONE"}
            ],
            "indications": {
                "Acute Asthma Exacerbation (1–2 mg/kg/day; calculated at 2 mg/kg Q24H)": {"dose_mg_kg_day": 2.0, "freq": 1, "max_single": 60.0, "max_daily": 60.0},
                "Acute Asthma Exacerbation (Divided: 2 mg/kg/day Q12H)": {"dose_mg_kg_day": 2.0, "freq": 2, "max_single": 30.0, "max_daily": 60.0},
                "Mild-to-Moderate Croup (1 mg/kg Single Dose)": {"dose_mg_kg_dose": 1.0, "freq": 1, "max_single": 60.0, "max_daily": 60.0}
            },
            "forms": {
                "Oral Syrup 15 mg / 5 mL (3 mg / mL)": {"type": "liquid", "conc_mg": 15, "conc_ml": 5},
                "Oral Solution 5 mg / 5 mL (1 mg / mL)": {"type": "liquid", "conc_mg": 5, "conc_ml": 5},
                "Orally Disintegrating Tablet 15 mg": {"type": "solid", "strength_mg": 15, "unit": "tablet"}
            },
            "counseling": [
                "Administer with food or milk to prevent GI upset; give single daily doses in the morning to mimic endogenous cortisol and reduce insomnia.",
                "Short courses (3–5 days) do not require tapering."
            ]
        },
        "Dexamethasone": {
            "category": "Corticosteroids",
            "sources": [
                {"title": "Cochrane Systematic Review: Glucocorticoids for Croup in Children", "url": "https://doi.org/10.1002/14651858.CD001955.pub5"},
                {"title": "DailyMed FDA Label: Dexamethasone Elixir", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=DEXAMETHASONE"}
            ],
            "indications": {
                "Croup — Mild, Moderate, or Severe (0.6 mg/kg Single Dose)": {"dose_mg_kg_dose": 0.6, "freq": 1, "max_single": 16.0, "max_daily": 16.0},
                "Croup — Low-Dose Alternative (0.15 mg/kg Single Dose)": {"dose_mg_kg_dose": 0.15, "freq": 1, "max_single": 16.0, "max_daily": 16.0},
                "Acute Asthma Exacerbation (0.6 mg/kg/day Q24H for 1–2 Days)": {"dose_mg_kg_dose": 0.6, "freq": 1, "max_single": 16.0, "max_daily": 16.0}
            },
            "forms": {
                "Oral Elixir / Solution 0.5 mg / 5 mL (0.1 mg / mL)": {"type": "liquid", "conc_mg": 0.5, "conc_ml": 5},
                "Oral Syrup 2 mg / 5 mL (0.4 mg / mL)": {"type": "liquid", "conc_mg": 2, "conc_ml": 5},
                "Oral Concentrated Solution 1 mg / 1 mL": {"type": "liquid", "conc_mg": 1, "conc_ml": 1},
                "Oral Tablet 4 mg": {"type": "solid", "strength_mg": 4, "unit": "tablet"},
                "Oral Tablet 0.5 mg": {"type": "solid", "strength_mg": 0.5, "unit": "tablet"}
            },
            "counseling": [
                "Note: 0.5 mg/5 mL elixir requires large volumes for bigger children; consider 2 mg/5 mL syrup or 4 mg tablets.",
                "Long biological half-life (36–54 hours) allows a 1- to 2-day course to equal a 5-day course of prednisolone."
            ]
        },
        "Betamethasone": {
            "category": "Corticosteroids",
            "sources": [
                {"title": "Medicines.org.uk (SmPC): Betamethasone 500 mcg Soluble Tablets", "url": "https://www.medicines.org.uk/emc/search?q=betamethasone"}
            ],
            "indications": {
                "Acute Allergic / Inflammatory Conditions (0.1 mg/kg/day Divided Q8H)": {"dose_mg_kg_day": 0.1, "freq": 3, "max_single": 1.5, "max_daily": 4.5},
                "Mild Inflammatory / Allergic Regimen (0.05 mg/kg/day Divided Q12H)": {"dose_mg_kg_day": 0.05, "freq": 2, "max_single": 1.2, "max_daily": 2.4}
            },
            "forms": {
                "Oral Syrup / Drops 0.6 mg / 5 mL (0.12 mg / mL)": {"type": "liquid", "conc_mg": 0.6, "conc_ml": 5},
                "Oral Tablet 0.5 mg": {"type": "solid", "strength_mg": 0.5, "unit": "tablet"},
                "Oral Tablet 0.6 mg": {"type": "solid", "strength_mg": 0.6, "unit": "tablet"}
            },
            "counseling": [
                "Potent long-acting glucocorticoid (approx. 0.6 mg betamethasone = 4 mg methylprednisolone = 5 mg prednisolone).",
                "Administer with food; avoid prolonged use in pediatrics due to HPA-axis and growth suppression."
            ]
        },
        "Hydrocortisone": {
            "category": "Corticosteroids",
            "sources": [
                {"title": "Endocrine Society Clinical Practice Guideline: Congenital Adrenal Hyperplasia", "url": "https://doi.org/10.1210/jc.2018-01865"},
                {"title": "DailyMed FDA Label: Hydrocortisone Tablets", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=HYDROCORTISONE"}
            ],
            "indications": {
                "Anti-Inflammatory / Immunosuppressive (2.5 mg/kg/day Divided Q8H)": {"dose_mg_kg_day": 2.5, "freq": 3, "max_single": 20.0, "max_daily": 60.0},
                "Physiologic Adrenal Replacement Approx. (~0.5 mg/kg/day Divided TID)": {"dose_mg_kg_day": 0.5, "freq": 3, "max_single": 10.0, "max_daily": 30.0}
            },
            "forms": {
                "Compounded Oral Suspension 1 mg / 1 mL (5 mg / 5 mL)": {"type": "liquid", "conc_mg": 1, "conc_ml": 1},
                "Oral Tablet 5 mg": {"type": "solid", "strength_mg": 5, "unit": "tablet"},
                "Oral Tablet 10 mg": {"type": "solid", "strength_mg": 10, "unit": "tablet"},
                "Oral Tablet 20 mg": {"type": "solid", "strength_mg": 20, "unit": "tablet"}
            },
            "counseling": [
                "Take with food or milk to decrease GI upset.",
                "Never abruptly discontinue chronic adrenal replacement therapy (risk of life-threatening adrenal crisis; stress-dosing required during febrile illness)."
            ]
        },

        # =====================================================================
        # CATEGORY 6: RESPIRATORY & BRONCHODILATORS
        # =====================================================================
        "Montelukast (Singulair)": {
            "category": "Respiratory & Bronchodilators",
            "sources": [
                {"title": "GINA Global Strategy for Asthma Management and Prevention", "url": "https://ginasthma.org/reports/"},
                {"title": "DailyMed FDA Label: Montelukast Sodium (Boxed Warning)", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=MONTELUKAST"}
            ],
            "indications": {
                "Asthma Maintenance / Allergic Rhinitis (Auto Age-Adjusted Evening Dose)": {
                    "type": "age_bands",
                    "bands": [
                        {"min_mo": 6.0, "max_mo": 72.0, "dose_mg": 4.0, "freq": 1, "note": "Age 6 months – 5 years: 4 mg (granules or chewable) once daily in the evening"},
                        {"min_mo": 72.0, "max_mo": 180.0, "dose_mg": 5.0, "freq": 1, "note": "Age 6–14 years: 5 mg chewable tablet once daily in the evening"},
                        {"min_mo": 180.0, "max_mo": 9999.0, "dose_mg": 10.0, "freq": 1, "note": "Age ≥ 15 years: 10 mg tablet once daily in the evening"}
                    ]
                }
            },
            "forms": {
                "Oral Granules Packet 4 mg": {"type": "solid", "strength_mg": 4, "unit": "packet"},
                "Chewable Tablet 4 mg": {"type": "solid", "strength_mg": 4, "unit": "tablet"},
                "Chewable Tablet 5 mg": {"type": "solid", "strength_mg": 5, "unit": "tablet"},
                "Oral Tablet 10 mg": {"type": "solid", "strength_mg": 10, "unit": "tablet"}
            },
            "counseling": [
                "🛑 FDA Boxed Warning: Monitor closely for neuropsychiatric events (nightmares, agitation, aggression, sleep disturbances, depression); discontinue immediately if these occur.",
                "Oral granules may be administered directly into the mouth or mixed with a spoonful of cold/room-temperature soft food (applesauce, carrots, rice, or breast milk/formula) and given within 15 minutes."
            ]
        },
        "Salbutamol / Albuterol (Ventolin Oral)": {
            "category": "Respiratory & Bronchodilators",
            "sources": [
                {"title": "DailyMed FDA Label: Albuterol Sulfate Syrup", "url": "https://dailymed.nlm.nih.gov/dailymed/search.cfm?labeltype=all&query=ALBUTEROL+SYRUP"},
                {"title": "Medicines.org.uk (SmPC): Ventolin 2 mg/5 mL Syrup", "url": "https://www.medicines.org.uk/emc/search?q=ventolin+syrup"}
            ],
            "indications": {
                "Bronchospasm (Weight-Based: 0.1 mg/kg/dose TID; Max 2–4 mg/dose)": {"dose_mg_kg_dose": 0.1, "freq": 3, "max_single": 4.0, "max_daily": 12.0}
            },
            "forms": {
                "Oral Syrup 2 mg / 5 mL": {"type": "liquid", "conc_mg": 2, "conc_ml": 5},
                "Oral Tablet 2 mg": {"type": "solid", "strength_mg": 2, "unit": "tablet"},
                "Oral Tablet 4 mg": {"type": "solid", "strength_mg": 4, "unit": "tablet"}
            },
            "counseling": [
                "Clinical Note: Inhaled salbutamol via MDI + spacer is strongly preferred over oral syrup due to faster onset and fewer systemic adverse effects.",
                "Oral salbutamol commonly causes skeletal muscle tremor, tachycardia, and hyperactivity/restlessness in children."
            ]
        }
    }

    @classmethod
    def calculate_from_diagnosis(
        cls,
        drug: str,
        diagnosis: str,
        form_name: str,
        weight_kg: float,
        age_months: float
    ) -> Dict[str, Any]:
        drug_data = cls.GUIDELINES.get(drug, {})
        rule = drug_data.get("indications", {}).get(diagnosis)
        form = drug_data.get("forms", {}).get(form_name)
        counseling = drug_data.get("counseling", [])
        sources = drug_data.get("sources", [])

        if not rule or not form:
            return {"error": "Selected indication or dosage form not found."}

        alerts = []
        formula_explanation = ""
        rule_type = rule.get("type", "standard")

        # 1. AGE-BANDED LOGIC
        if rule_type == "age_bands":
            matched_band = None
            for b in rule["bands"]:
                if b["min_mo"] <= age_months < b["max_mo"]:
                    matched_band = b
                    break
            if not matched_band:
                min_allowed = rule["bands"][0]["min_mo"]
                return {
                    "error": f"🛑 Contraindicated / Not Recommended: Patient age ({age_months:.1f} months) is below the minimum approved age ({min_allowed:g} months) for {drug}."
                }
            raw_single = matched_band["dose_mg"]
            freq = matched_band["freq"]
            raw_daily = raw_single * freq
            max_single = raw_single
            max_daily = raw_daily
            formula_explanation = f"Age-Banded Guideline ({matched_band['note']})"

        # 2. KETOTIFEN HYBRID AGE/WEIGHT LOGIC
        elif rule_type == "ketotifen_hybrid":
            if age_months < 6.0:
                return {"error": "🛑 Ketotifen is not recommended for infants under 6 months of age."}
            elif age_months < 36.0:
                freq = 2
                raw_single = weight_kg * 0.05
                raw_daily = raw_single * freq
                max_single = 1.0
                max_daily = 2.0
                formula_explanation = f"Infant/Toddler (6mo–3yrs): 0.05 mg/kg/dose × {weight_kg:.1f} kg = {raw_single:.2f} mg BID"
            else:
                freq = 2
                raw_single = 1.0
                raw_daily = 2.0
                max_single = 1.0
                max_daily = 2.0
                formula_explanation = "Child (≥ 3 years): Standard flat dose of 1 mg twice daily"

        # 3. WEIGHT-BANDED LOGIC
        elif rule_type == "weight_bands":
            freq = rule.get("freq", 1)
            max_single = rule.get("max_single", 0.0)
            max_daily = rule.get("max_daily", 0.0)
            matched_band = None
            for b in rule["bands"]:
                if b["min_wt"] <= weight_kg <= b["max_wt"]:
                    matched_band = b
                    break
            if matched_band:
                raw_single = matched_band["dose_mg"]
                raw_daily = raw_single * freq
                formula_explanation = f"Weight-Band ({matched_band['min_wt']:g}–{matched_band['max_wt']:g} kg) → {raw_single:g} mg per dose"
            else:
                fb = rule.get("fallback_mg_kg", 0.15)
                raw_single = weight_kg * fb
                raw_daily = raw_single * freq
                alerts.append(f"Patient weight ({weight_kg:.1f} kg) is below standard weight-band threshold; calculated using {fb} mg/kg fallback.")
                formula_explanation = f"{fb} mg/kg × {weight_kg:.1f} kg = {raw_single:.2f} mg"

        # 4. STANDARD WEIGHT-BASED LOGIC (mg/kg/day or mg/kg/dose)
        else:
            freq = rule.get("freq", 2)
            max_single = rule.get("max_single", 0.0)
            max_daily = rule.get("max_daily", 0.0)

            if "dose_mg_kg_day" in rule:
                mg_kg_day = rule["dose_mg_kg_day"]
                raw_daily = weight_kg * mg_kg_day
                raw_single = raw_daily / freq
                formula_explanation = f"({mg_kg_day:g} mg/kg/day × {weight_kg:.2f} kg) ÷ {freq} doses/day = {raw_single:.1f} mg/dose ({raw_daily:.1f} mg/day)"
            else:
                mg_kg_dose = rule["dose_mg_kg_dose"]
                raw_single = weight_kg * mg_kg_dose
                raw_daily = raw_single * freq
                formula_explanation = f"{mg_kg_dose:g} mg/kg/dose × {weight_kg:.2f} kg = {raw_single:.1f} mg/dose × {freq}/day ({raw_daily:.1f} mg/day)"

        # APPLY CEILING CAPS ACCURATELY
        final_single = raw_single
        final_daily = raw_daily

        if max_single > 0 and final_single > max_single:
            alerts.append(f"Calculated single dose ({raw_single:.1f} mg) exceeded single-dose limit; capped at {max_single:g} mg/dose.")
            final_single = max_single
            final_daily = final_single * freq

        if max_daily > 0 and final_daily > max_daily:
            alerts.append(f"Calculated daily dose ({final_daily:.1f} mg/day) exceeded daily maximum; capped at {max_daily:g} mg/day.")
            final_daily = max_daily
            final_single = final_daily / freq

        # CHECK SMX-TMP CO-COMPONENT DISPLAY
        smx_ratio = rule.get("smx_ratio")
        co_component_str = ""
        if smx_ratio:
            smx_single = final_single * smx_ratio
            smx_daily = final_daily * smx_ratio
            co_component_str = f" (plus {smx_single:.0f} mg SMX/dose; {smx_daily:.0f} mg SMX/day)"

        # FORMULATION CONVERSION (LIQUID VS SOLID)
        if form["type"] == "liquid":
            conc_mg = form["conc_mg"]
            conc_ml = form["conc_ml"]
            mg_per_ml = conc_mg / conc_ml
            vol_single = final_single / mg_per_ml
            vol_daily = final_daily / mg_per_ml
            dose_unit_str = f"{vol_single:.2f} mL"
            form_calc_details = {
                "form_type": "liquid",
                "vol_single": vol_single,
                "vol_daily": vol_daily,
                "conc_str": f"{conc_mg:g} mg / {conc_ml:g} mL ({mg_per_ml:g} mg/mL)"
            }
        else:
            strength_mg = form["strength_mg"]
            unit_label = form.get("unit", "tablet")
            count_single = final_single / strength_mg
            count_daily = final_daily / strength_mg
            dose_unit_str = f"{count_single:.2f} {unit_label}(s)"
            
            remainder = (count_single * 2) % 1
            if count_single < 0.5 or (remainder > 0.15 and remainder < 0.85):
                alerts.append(f"Calculated solid dose ({count_single:.2f} {unit_label}s) requires awkward splitting. Consider switching to an oral liquid suspension.")

            form_calc_details = {
                "form_type": "solid",
                "unit_label": unit_label,
                "count_single": count_single,
                "count_daily": count_daily,
                "strength_str": f"{strength_mg:g} mg per {unit_label}"
            }

        return {
            "drug": drug,
            "diagnosis": diagnosis,
            "form_name": form_name,
            "final_single_mg": final_single,
            "final_daily_mg": final_daily,
            "co_component_str": co_component_str,
            "formula_explanation": formula_explanation,
            "dose_unit_str": dose_unit_str,
            "form_details": form_calc_details,
            "freq": freq,
            "interval_hours": round(24 / freq, 1),
            "alerts": alerts,
            "counseling": counseling,
            "sources": sources
        }

class ClinicalReportGenerator:
    @staticmethod
    def _md_bold_to_html(text: str) -> str:
        escaped = html.escape(text)
        return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped)

    @classmethod
    def generate_html_report(
        cls,
        patient_meta: Dict[str, str],
        dosing_summary: Optional[Dict[str, Any]],
        interaction_summary: Optional[Dict[str, Any]],
        monograph_data: Optional[Dict[str, Any]]
    ) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        dosing_html = "<p><em>No diagnosis-driven dosing calculation recorded in this session.</em></p>"
        if dosing_summary:
            metrics_rows = "".join(f"<tr><th>{html.escape(k)}</th><td><strong>{html.escape(str(v))}</strong></td></tr>" for k, v in dosing_summary.get("metrics", {}).items())
            params_rows = "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>" for k, v in dosing_summary.get("parameters", {}).items())
            alerts_html = f'<div class="alert-box"><strong>⚠️ Guideline Safety Alerts:</strong><ul>{"".join(f"<li>{cls._md_bold_to_html(a)}</li>" for a in dosing_summary["alerts"])}</ul></div>' if dosing_summary.get("alerts") else ""

            sources_list = dosing_summary.get("sources", [])
            sources_html = ""
            if sources_list:
                links_li = "".join(
                    f'<li><a href="{html.escape(s["url"])}" target="_blank" rel="noopener noreferrer">{html.escape(s["title"])}</a> — <span style="color:#64748b;font-size:11px;">{html.escape(s["url"])}</span></li>'
                    for s in sources_list
                )
                sources_html = f'<div class="source-box"><strong>📚 Clinical Guideline & Reference Sources:</strong><ul>{links_li}</ul></div>'

            dosing_html = f"""
                <div class="section-subtitle">Indication / Diagnosis Engine: {html.escape(dosing_summary.get('mode', 'Standard'))}</div>
                {alerts_html}
                <div class="two-col">
                    <div><h4>Patient & Formulation Parameters</h4><table class="data-table">{params_rows}</table></div>
                    <div><h4>Calculated Regimen</h4><table class="data-table">{metrics_rows}</table></div>
                </div>
                <div class="sig-box"><strong>Prescription Sig Summary:</strong><br/>{cls._md_bold_to_html(dosing_summary.get('sig_summary', ''))}</div>
                {sources_html}
            """

        counsel_html = ""
        if dosing_summary and dosing_summary.get("counseling"):
            c_items = "".join(f"<li>{cls._md_bold_to_html(c)}</li>" for c in dosing_summary["counseling"])
            counsel_html = f'<div class="report-section"><h2>Patient Counseling & Education Requirements</h2><ul>{c_items}</ul></div>'

        inter_html = "<p><em>No multi-drug interaction analysis recorded in this session.</em></p>"
        if interaction_summary and interaction_summary.get("pair_results"):
            norm_rows = "".join(f"<tr><td>{html.escape(p['input_name'])}</td><td><strong>{html.escape(p['rxnorm']['normalized_name'].title())}</strong></td><td>{html.escape(p['rxnorm']['rxcui'])}</td><td>{'Loaded' if p.get('fda_data') else 'Class Rules Only'}</td></tr>" for p in interaction_summary.get("profiles", []))
            pair_cards = ""
            for res in interaction_summary["pair_results"]:
                rank = res["severity_rank"]
                card_cls = "pair-high" if rank == 2 else ("pair-mod" if rank == 1 else "pair-clear")
                badge = "MAJOR / CONTRAINDICATED" if rank == 2 else ("MODERATE / PRECAUTION" if rank == 1 else "NO DIRECT LABEL CONFLICT")
                findings_list = f"<ul>{''.join(f'<li><strong>[{html.escape(f['source'])}]:</strong> {cls._md_bold_to_html(f['excerpt'])}</li>' for f in res['findings'])}</ul>" if res["findings"] else ""
                pair_cards += f'<div class="pair-card {card_cls}"><div class="pair-header"><span class="badge">{badge}</span><strong>{html.escape(res["pair"])}</strong> — <em>{html.escape(res["severity"])}</em></div>{findings_list}</div>'

            inter_html = f'<h4>Evaluated Medication Regimen (RxNorm Standardized)</h4><table class="data-table"><thead><tr><th>Entered Name</th><th>Standardized Generic Ingredient</th><th>RxCUI</th><th>FDA Monograph</th></tr></thead><tbody>{norm_rows}</tbody></table><h4>Pairwise Interaction Findings ({len(interaction_summary["pair_results"])} Pairs Evaluated)</h4>{pair_cards}'

        mono_html = ""
        if monograph_data:
            boxed_html = f'<div class="pair-card pair-high"><strong>🛑 FDA BOXED WARNING:</strong><br/>{html.escape(monograph_data["boxed_warning"][:1200])}</div>' if monograph_data.get("boxed_warning") else ""
            mono_html = f"""
                <div class="report-section">
                    <h2>Primary Medication Monograph Highlights: {html.escape(monograph_data.get('generic_name', '').title())}</h2>
                    <table class="data-table">
                        <tr><th>Brand Name(s)</th><td>{html.escape(monograph_data.get('brand_name', 'N/A')[:100])}</td><th>Route(s)</th><td>{html.escape(monograph_data.get('route', 'N/A'))}</td></tr>
                        <tr><th>Pharmacologic Class</th><td>{html.escape(monograph_data.get('pharm_class', 'N/A')[:100])}</td><th>Manufacturer</th><td>{html.escape(monograph_data.get('manufacturer', 'N/A')[:80])}</td></tr>
                    </table>
                    {boxed_html}
                    <h4>Contraindications Summary</h4><p class="mono-excerpt">{html.escape(monograph_data.get('contraindications', 'N/A')[:900])}</p>
                    <h4>Dosage & Administration Overview</h4><p class="mono-excerpt">{html.escape(monograph_data.get('dosage_and_admin', 'N/A')[:900])}</p>
                </div>
            """

        notes_html = f'<div class="report-section"><h2>Clinical Assessment & Notes</h2><div class="sig-box">{html.escape(patient_meta.get("clinical_notes", "")).replace(chr(10), "<br/>")}</div></div>' if patient_meta.get("clinical_notes") else ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Clinical Indication-Driven Dosing Report</title>
    <style>
        :root {{ --primary: #1a365d; --border: #cbd5e1; --bg-light: #f8fafc; }}
        * {{ box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #1e293b; line-height: 1.45; margin: 0; padding: 25px; font-size: 13px; }}
        .report-container {{ max-width: 900px; margin: 0 auto; }}
        .print-banner {{ background: #eef2ff; border: 1px solid #c7d2fe; padding: 10px 15px; border-radius: 6px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }}
        .print-btn {{ background: #2563eb; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-weight: 600; font-size: 13px; }}
        .report-header {{ border-bottom: 3px solid var(--primary); padding-bottom: 12px; margin-bottom: 18px; display: flex; justify-content: space-between; align-items: flex-end; }}
        .report-header h1 {{ margin: 0; color: var(--primary); font-size: 22px; }}
        .meta-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; background: var(--bg-light); border: 1px solid var(--border); padding: 12px; border-radius: 6px; margin-bottom: 20px; }}
        .meta-item label {{ display: block; font-size: 11px; color: #64748b; text-transform: uppercase; font-weight: 600; }}
        .meta-item span {{ font-weight: 700; font-size: 13.5px; color: #0f172a; }}
        .report-section {{ margin-bottom: 22px; page-break-inside: avoid; }}
        h2 {{ color: var(--primary); font-size: 16px; border-bottom: 1px solid var(--border); padding-bottom: 5px; margin-top: 0; margin-bottom: 12px; }}
        h4 {{ margin: 10px 0 6px 0; font-size: 13px; color: #334155; }}
        .section-subtitle {{ font-weight: 600; color: #475569; margin-bottom: 10px; }}
        .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 12px; }}
        .data-table {{ width: 100%; border-collapse: collapse; margin-bottom: 10px; font-size: 12.5px; }}
        .data-table th, .data-table td {{ border: 1px solid var(--border); padding: 6px 10px; text-align: left; }}
        .data-table th {{ background: var(--bg-light); font-weight: 600; width: 42%; }}
        .sig-box {{ background: #f0f9ff; border-left: 4px solid #0284c7; padding: 10px 14px; border-radius: 4px; margin-top: 8px; }}
        .source-box {{ background: #f0fdf4; border-left: 4px solid #16a34a; padding: 10px 14px; border-radius: 4px; margin-top: 8px; }}
        .source-box ul {{ margin: 4px 0 0 0; padding-left: 18px; }}
        .alert-box {{ background: #fffbeb; border-left: 4px solid #f59e0b; padding: 8px 12px; margin-bottom: 10px; color: #92400e; }}
        .pair-card {{ border: 1px solid var(--border); border-radius: 5px; padding: 10px 14px; margin-bottom: 10px; page-break-inside: avoid; }}
        .pair-high {{ background: #fef2f2; border-left: 5px solid #dc2626; }}
        .pair-mod {{ background: #fffbeb; border-left: 5px solid #d97706; }}
        .pair-clear {{ background: #f0fdf4; border-left: 5px solid #16a34a; }}
        .badge {{ display: inline-block; padding: 2px 6px; font-size: 10.5px; font-weight: 700; border-radius: 3px; margin-right: 6px; background: rgba(0,0,0,0.08); }}
        .mono-excerpt {{ background: var(--bg-light); border: 1px solid var(--border); padding: 8px 12px; border-radius: 4px; font-size: 12px; white-space: pre-line; }}
        .signoff-grid {{ margin-top: 35px; padding-top: 15px; border-top: 1px solid var(--border); display: grid; grid-template-columns: 1fr 1fr; gap: 40px; page-break-inside: avoid; }}
        .sig-line {{ border-bottom: 1px solid #475569; height: 28px; margin-bottom: 4px; }}
        .disclaimer-footer {{ margin-top: 25px; font-size: 11px; color: #64748b; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 10px; }}
        @media print {{ body {{ padding: 0; }} .no-print {{ display: none !important; }} }}
    </style>
</head>
<body>
    <div class="report-container">
        <div class="print-banner no-print">
            <span>📄 <strong>Print-Ready Clinical Report:</strong> Click to save as PDF or print.</span>
            <button class="print-btn" onclick="window.print()">🖨️ Print / Save as PDF</button>
        </div>
        <div class="report-header">
            <div>
                <h1>Clinical Indication-Driven Dosing Report</h1>
                <div class="sub">Guideline-Based Dosing Engine (Weight, Age & Diagnosis)</div>
            </div>
            <div style="text-align: right; font-size: 12px; color: #475569;"><strong>Date:</strong> {timestamp}</div>
        </div>
        <div class="meta-grid">
            <div class="meta-item"><label>Patient Name</label><span>{html.escape(patient_meta.get('patient_name', ''))}</span></div>
            <div class="meta-item"><label>Age / Weight</label><span>{html.escape(patient_meta.get('age_sex', ''))} | {html.escape(patient_meta.get('anthropometrics', ''))}</span></div>
            <div class="meta-item"><label>Indication</label><span>{html.escape(patient_meta.get('indication', ''))}</span></div>
            <div class="meta-item"><label>Clinician</label><span>{html.escape(patient_meta.get('clinician_name', ''))}</span></div>
        </div>
        <div class="report-section"><h2>1. Indication-Driven Dosing Regimen</h2>{dosing_html}</div>
        {counsel_html}
        <div class="report-section"><h2>2. Multi-Drug Interaction Analysis</h2>{inter_html}</div>
        {mono_html}
        {notes_html}
        <div class="signoff-grid">
            <div><div class="sig-line"></div><strong>Clinician Signature:</strong></div>
            <div><div class="sig-line"></div><strong>Date & Stamp</strong></div>
        </div>
        <div class="disclaimer-footer">Clinical Decision Support Tool — Verify all calculations against institutional protocols.</div>
    </div>
</body>
</html>"""

def main():
    st.title("💊 Clinical Indication-Driven Dosing System")
    
    tab_dosing, tab_monograph, tab_interactions, tab_report = st.tabs([
        "🎯 Indication Dosing",
        "📄 FDA Monograph",
        "⚡ Interaction Checker",
        "📥 Print Report"
    ])

    with tab_dosing:
        col_in, col_out = st.columns([1, 1])

        with col_in:
            st.markdown("#### 1. Patient Demographics")
            a_col1, a_col2 = st.columns([2, 1])
            age_unit = a_col2.selectbox("Age Unit", ["Years", "Months"], index=0)
            age_val = a_col1.number_input("Patient Age", min_value=0.0, max_value=216.0, value=5.0, step=0.5)

            w_col1, w_col2 = st.columns([2, 1])
            weight_val = w_col1.number_input("Patient Weight", min_value=0.5, max_value=300.0, value=18.0, step=0.5)
            weight_unit = w_col2.selectbox("Weight Unit", ["kg", "lbs"])
            weight_kg = weight_val if weight_unit == "kg" else weight_val / 2.20462

            peds_validation = PediatricWeightValidator.validate_pediatric_weight(age_val, age_unit, weight_kg)
            age_months = peds_validation["age_months"]
            allow_calc = True

            if peds_validation["status"] == "critical":
                for msg in peds_validation["messages"]: st.error(msg)
                allow_calc = st.checkbox("⚠️ Clinician Override: Confirm entered weight is accurate.", value=False)
            elif peds_validation["status"] == "warning":
                for msg in peds_validation["messages"]: st.warning(msg)

            st.markdown("#### 2. Medication Selection")
            
            all_categories = sorted(list(set(data.get("category", "Other") for data in IndicationDosingEngine.GUIDELINES.values())))
            selected_category = st.selectbox("Select Drug Category", all_categories)
            
            category_drugs = [drug for drug, data in IndicationDosingEngine.GUIDELINES.items() if data.get("category", "Other") == selected_category]
            selected_drug = st.selectbox("Select Medication", sorted(category_drugs))
            
            available_diagnoses = list(IndicationDosingEngine.GUIDELINES[selected_drug]["indications"].keys())
            selected_diagnosis = st.selectbox("Select Indication", available_diagnoses)

            available_forms = list(IndicationDosingEngine.GUIDELINES[selected_drug]["forms"].keys())
            selected_form = st.selectbox("Select Dosage Form / Strength", available_forms)

        with col_out:
            st.markdown("#### 3. Guideline Regimen")
            if not allow_calc:
                st.info("🔒 Calculation paused due to weight plausibility warning. Check override box to proceed.")
            else:
                res = IndicationDosingEngine.calculate_from_diagnosis(
                    selected_drug, selected_diagnosis, selected_form, weight_kg, age_months
                )
                if "error" in res:
                    st.error(res["error"])
                else:
                    st.markdown(f'<div class="formula-box">📐 <strong>Formula Applied:</strong> {res["formula_explanation"]}</div>', unsafe_allow_html=True)
                    
                    if res.get("sources"):
                        links_html = " | ".join(
                            f'<a href="{s["url"]}" target="_blank" rel="noopener noreferrer">{s["title"]}</a>'
                            for s in res["sources"]
                        )
                        st.markdown(f'<div class="source-box">📚 <strong>Guideline References:</strong> {links_html}</div>', unsafe_allow_html=True)

                    for alert in res["alerts"]: st.warning(f"⚠️ {alert}")
                    
                    r1, r2 = st.columns(2)
                    r1.metric("Single Dose", f"{res['final_single_mg']:.1f} mg")
                    r2.metric("Total Daily Dose", f"{res['final_daily_mg']:.1f} mg/day")

                    fd = res["form_details"]
                    f1, f2 = st.columns(2)
                    if fd["form_type"] == "liquid":
                        f1.metric("Liquid Volume / Dose", f"{fd['vol_single']:.2f} mL", f"Every {res['interval_hours']:g} hours")
                        f2.metric("Total Daily Volume", f"{fd['vol_daily']:.2f} mL/day", f"{fd['conc_str']}")
                        sig_form_desc = f"**{fd['vol_single']:.2f} mL** of {fd['conc_str']}"
                    else:
                        unit_lbl = fd["unit_label"]
                        f1.metric("Form Units / Dose", f"{fd['count_single']:.2f} {unit_lbl}(s)", f"Every {res['interval_hours']:g} hours")
                        f2.metric("Total Daily Units", f"{fd['count_daily']:.2f} {unit_lbl}(s)/day", f"{fd['strength_str']}")
                        sig_form_desc = f"**{fd['count_single']:.2f} {unit_lbl}(s)** ({fd['strength_str']})"

                    sig_summary = (
                        f"Administer **{res['final_single_mg']:.1f} mg**{res['co_component_str']} "
                        f"({sig_form_desc}) every **{res['interval_hours']:g} hours** "
                        f"({res['freq']}x daily) for **{selected_diagnosis}**."
                    )
                    st.info(f"**Prescription Sig Summary:**\n\n{sig_summary}")

                    if res.get("counseling"):
                        st.markdown("#### 🗣️ Patient Counseling & Education")
                        counseling_html = "<ul>" + "".join([f"<li>{c}</li>" for c in res["counseling"]]) + "</ul>"
                        st.markdown(f'<div class="counseling-box">{counseling_html}</div>', unsafe_allow_html=True)

                    st.session_state.latest_dosing = {
                        "mode": f"{selected_drug} Guideline Dosing",
                        "parameters": {
                            "Category": selected_category,
                            "Medication": selected_drug,
                            "Indication": selected_diagnosis,
                            "Dosage Form": selected_form,
                            "Patient Age": f"{age_val:g} {age_unit.lower()}",
                            "Patient Weight": f"{weight_kg:.2f} kg",
                            "Formula Applied": res["formula_explanation"]
                        },
                        "metrics": {
                            "Single Dose": f"{res['final_single_mg']:.1f} mg{res['co_component_str']}",
                            "Total Daily Dose": f"{res['final_daily_mg']:.1f} mg/day",
                            "Prescribed Amount / Dose": res["dose_unit_str"]
                        },
                        "alerts": res["alerts"],
                        "sig_summary": sig_summary,
                        "counseling": res.get("counseling", []),
                        "sources": res.get("sources", [])
                    }
                    st.session_state.latest_indication = selected_diagnosis

            api_search_term = selected_drug.split(" (")[0].split(" /")[0]
            if st.session_state.get("last_fetched_drug") != selected_drug:
                with st.spinner(f"Auto-fetching FDA Monograph for {api_search_term}..."):
                    st.session_state.drug_data = DrugDataClient.fetch_drug_label(api_search_term)
                    st.session_state.last_fetched_drug = selected_drug

    with tab_monograph:
        data = st.session_state.get("drug_data")
        if not data:
            st.warning(f"No FDA Monograph found in the US OpenFDA database for '{api_search_term}'. Refer to the direct EMA/SmPC reference links on the Indication Dosing tab.")
        else:
            st.subheader(data['generic_name'].title())
            st.write(data['indications'])
            if data['boxed_warning']: st.markdown(f'<div class="boxed-warning"><h4>🛑 Boxed Warning</h4>{data["boxed_warning"][:1000]}</div>', unsafe_allow_html=True)
            with st.expander("Dosage & Administration Guidelines"):
                st.write(data['dosage_and_admin'])
            with st.expander("Contraindications & Warnings"):
                st.write(data['contraindications'])
                st.write(data['warnings'])

    with tab_interactions:
        st.subheader("⚡ Pairwise Interaction Checker")
        med_input = st.text_area("Enter medications (comma-separated):", value="Clarithromycin, Domperidone")
        if st.button("Check Interactions"):
            meds = [m.strip() for m in med_input.split(",") if m.strip()]
            profiles = [{"input_name": m, "rxnorm": DrugDataClient.resolve_rxnorm_ingredient(m), "fda_data": DrugDataClient.fetch_drug_label(m)} for m in meds]
            results = [PairwiseInteractionEngine.evaluate_pair(a, b) for a, b in list(combinations(profiles, 2))]
            st.session_state.latest_interactions = {"profiles": profiles, "pair_results": results}
            for r in results:
                st.markdown(f"**{r['pair']}** — *{r['severity']}*")
                for f in r["findings"]: st.write(f"- {f['excerpt']}")

    with tab_report:
        st.subheader("📥 Export & Print Report")
        col_meta1, col_meta2 = st.columns(2)
        with col_meta1:
            pt_name = st.text_input("Patient Name", value="Patient #402")
            pt_meta_str = st.text_input("Age / Sex", value=f"{age_val:g} {age_unit.lower()} / Male")
        with col_meta2:
            pt_anthro_str = st.text_input("Weight Summary", value=f"{weight_kg:.1f} kg")
            clinician = st.text_input("Clinician Name", value="Clinician")
        notes = st.text_area("Notes", value="Verified indication-driven dosing & patient counseling points.")

        html_out = ClinicalReportGenerator.generate_html_report(
            {"patient_name": pt_name, "age_sex": pt_meta_str, "anthropometrics": pt_anthro_str, "clinician_name": clinician, "indication": st.session_state.get('latest_indication', ''), "clinical_notes": notes},
            st.session_state.get("latest_dosing"),
            st.session_state.get("latest_interactions"),
            st.session_state.get("drug_data")
        )

        st.download_button("📥 Download HTML Report", data=html_out, file_name="clinical_dosing_report.html", mime="text/html", type="primary")
        st.components.v1.html(html_out, height=600, scrolling=True)

if __name__ == "__main__":
    main()
