# RegOS Knowledge Graph — FEA Pipeline Prompt

> **Architecture:** Fixed Entity Architecture (3-layer)
> **Based on:** Dr. Irina Adamchic (Accenture) + HyDE embedding projection
> **Version:** v2 — replaces the LLM extraction approach

---

## What This Prompt Asks Claude Code To Do

Build a Python pipeline that constructs the RegOS knowledge graph using the Fixed Entity Architecture. The pipeline does NOT use an LLM to extract entities from text. Instead, it:

1. Loads a human-defined ontology (concepts.json)
2. Generates HyDE embeddings for each concept (only LLM step)
3. Ingests all 144 Chapter 24 section files as document nodes with embeddings
4. Connects concepts to sections via cosine similarity (math, not LLM)
5. Extracts specific entities (thresholds, penalties, roles) via regex (not LLM)
6. Outputs Cypher load scripts or loads directly via Neo4j Python driver

---

## Prompt for Claude Code

```
You are building a knowledge graph pipeline for RegOS, a regulatory AI assistant
for Miami-Dade County Chapter 24 (Environmental Quality Control Board).

The architecture is Fixed Entity Architecture (FEA) with three layers:
- Layer 1: Fixed ontology concepts (defined in concepts.json)
- Layer 2: Section documents (144 .txt files in Chapter 24/ folder)
- Layer 3: Regex-extracted entities (thresholds, penalties, roles, standards)

=== TASK ===

Write a Python script (fea_pipeline.py) that:

1. LOADS ONTOLOGY
   - Read concepts.json (30 regulatory domain concepts)
   - Each concept has: id, name, description, primary_sections

2. GENERATES HyDE EMBEDDINGS (only LLM step)
   - For each concept, call the LLM to generate 3-5 hypothetical regulatory
     passages in the style of Chapter 24 statute text
   - Embed each passage using the embedding model
   - Average the embeddings to produce one concept embedding per concept
   - Store concept nodes in Neo4j with their HyDE embeddings

   HyDE prompt for each concept:
   "Generate 3 hypothetical passages that might appear in a Miami-Dade County
    environmental regulation about: {concept.description}
    Write in formal statutory language using phrases like 'shall', 'it shall
    be unlawful', 'is required to', 'no person shall'. Include specific
    details like section references, numeric thresholds, and role names."

3. INGESTS SECTION DOCUMENTS
   - Read all .txt files from "Chapter 24/" folder
   - Parse section number and title from filename
     (e.g., "Sec._24_42.6.___Fats__Oils_and_Grease..." -> number: "24-42.6")
   - Store full text, generate embedding, create Section node in Neo4j
   - Determine parent_section from number (e.g., "24-42" for "24-42.6")

4. CONNECTS LAYERS (cosine similarity, no LLM)
   - Compute cosine similarity between every Concept embedding and
     every Section embedding
   - Create RELATES_TO edges where similarity > threshold (start with 0.35)
   - Store the similarity score on the relationship

5. EXTRACTS LAYER 3 ENTITIES (regex, no LLM)
   - For each section, run these regex patterns:

   Thresholds:
     Pattern: (\d+[\.,]?\d*)\s*(mg/[lL]|ppm|percent|%|feet|foot|inches|
               gallons|acres|days|hours|minutes|years|months)
     Create: (:Threshold {value, unit, context, section_ref})
     Link: (:Section)-[:HAS_THRESHOLD]->(:Threshold)

   Penalty Amounts:
     Pattern: \$[\d,]+(?:\.\d{2})?\s*(?:per\s+(?:day|violation|offense))?
     Create: (:Penalty {amount, frequency, section_ref})
     Link: (:Section)-[:HAS_PENALTY]->(:Penalty)

   Section Cross-References:
     Pattern: [Ss]ec(?:tion)?\.?\s*24-[\d]+(?:\.[\d]+)?(?:\([\d]+\))?
     Create: (:Section)-[:REFERENCES]->(:Section)

   Role Names:
     Keywords: Director, Board, Property Owner, Tenant, Industrial User,
               Inspector, Operator, Transporter, Contractor, Consultant,
               Department, County Manager, applicant, permittee, licensee
     Create: (:Role {name, type})
     Link: (:Section)-[:MENTIONS_ROLE]->(:Role)

   External Standards:
     Pattern: \d+\s*(?:CFR|C\.F\.R\.)|Chapter\s+\d+.*?Florida Statutes|
              EPA Method|ASTM|ANSI
     Create: (:Standard {name, type})
     Link: (:Section)-[:CITES_STANDARD]->(:Standard)

   Legal Obligations:
     Pattern: (?:shall|must|is required|it shall be unlawful|no person shall|
              is prohibited)[^.]*\.
     Create: (:Obligation {text, type, section_ref})
     Link: (:Section)-[:CONTAINS_OBLIGATION]->(:Obligation)
     Type: "shall"/"must"/"is required" -> obligation
           "shall not"/"unlawful"/"prohibited" -> prohibition
           "may"/"is authorized" -> permission

6. CREATES PARENT HIERARCHY
   - For sections with subsections (e.g., 24-42.6 is child of 24-42):
     Create (:Section)-[:PART_OF]->(:Section)

7. OUTPUTS
   - Option A: Load directly into Neo4j using neo4j Python driver
   - Option B: Generate Cypher files in cypher/ folder

=== NEO4J SCHEMA ===

Node Labels:
  :Concept     {id, name, description, embedding}
  :Section     {id, number, title, full_text, embedding, parent_section}
  :Threshold   {value, unit, parameter, context, section_ref}
  :Penalty     {amount, frequency, type, section_ref}
  :Role        {name, type}          -- type: regulator|regulated|third_party
  :Standard    {name, type}          -- type: federal|state|local|industry
  :Obligation  {text, type, section_ref}  -- type: obligation|prohibition|permission

Relationships:
  (:Concept)-[:RELATES_TO {score: float}]->(:Section)
  (:Section)-[:REFERENCES]->(:Section)
  (:Section)-[:PART_OF]->(:Section)
  (:Section)-[:HAS_THRESHOLD]->(:Threshold)
  (:Section)-[:HAS_PENALTY]->(:Penalty)
  (:Section)-[:MENTIONS_ROLE]->(:Role)
  (:Section)-[:CITES_STANDARD]->(:Standard)
  (:Section)-[:CONTAINS_OBLIGATION]->(:Obligation)

Indexes:
  CREATE VECTOR INDEX concept_embedding FOR (c:Concept) ON c.embedding
  CREATE VECTOR INDEX section_embedding FOR (s:Section) ON s.embedding
  CREATE FULLTEXT INDEX section_text FOR (s:Section) ON EACH [s.full_text]
  CREATE CONSTRAINT FOR (c:Concept) REQUIRE c.id IS UNIQUE
  CREATE CONSTRAINT FOR (s:Section) REQUIRE s.id IS UNIQUE

=== CONFIGURATION ===

The script should accept these parameters:
  --concepts-file    Path to concepts.json (default: ./concepts.json)
  --sections-dir     Path to Chapter 24 folder (default: ./Chapter 24/)
  --neo4j-uri        Neo4j connection URI
  --neo4j-user       Neo4j username
  --neo4j-password   Neo4j password
  --similarity-threshold  Minimum cosine similarity for RELATES_TO (default: 0.35)
  --embedding-model  Which embedding model to use
  --llm-model        Which LLM to use for HyDE generation
  --output-mode      "direct" (load into Neo4j) or "cypher" (generate files)
  --output-dir       Directory for Cypher files (default: ./cypher/)

=== SUPER-NODE ELIMINATION ===

After computing all RELATES_TO edges, check if any Concept connects to
more than 50% of sections (>72 out of 144). If so, log a warning:
"SUPER-NODE DETECTED: {concept.name} matches {count} sections. Consider
splitting or removing this concept."

=== FILES IN THIS REPOSITORY ===

  concepts.json          -- 30 regulatory domain concepts (you'll create this)
  Chapter 24/            -- 144 section files (.docx.txt)
  fea_pipeline.py        -- The pipeline script (you'll create this)
  cypher/                -- Output directory for Cypher files

=== IMPORTANT NOTES ===

- The ONLY LLM usage is HyDE generation (~30 calls). Everything else is
  math (cosine similarity) and regex. This is intentional.
- Use MERGE (not CREATE) for all nodes so re-running is idempotent.
- Role nodes should be deduplicated (one "Director" node, not one per section).
- Obligation extraction may produce many results per section. That's fine —
  regulatory text is dense with obligations.
- The embedding model must be the same for concepts and sections.
- Log progress: "Processing concept 5/30...", "Ingesting section 42/144...", etc.
```

---

## concepts.json Template

Create this file before running the pipeline. Here are the 30 concepts:

```json
{
  "concepts": [
    {
      "id": "SEWER_DISCHARGE_LIMITS",
      "name": "Sewer Discharge Limits",
      "description": "Pollutant concentration limits for sanitary sewer discharge, pretreatment standards, industrial user discharge requirements, effluent standards",
      "primary_sections": ["24-42", "24-42.4", "24-42.5"]
    },
    {
      "id": "FOG_CONTROL",
      "name": "FOG Control Program",
      "description": "Fats, Oils and Grease management for food service establishments, grease interceptor installation and maintenance requirements, accelerated maintenance schedules",
      "primary_sections": ["24-42.6"]
    },
    {
      "id": "STORMWATER_MANAGEMENT",
      "name": "Stormwater Management",
      "description": "Stormwater utility creation, discharge standards, management system recertification, BMP requirements, stormwater fees and billing",
      "primary_sections": ["24-42.8", "24-51", "24-21.1"]
    },
    {
      "id": "WELLFIELD_PROTECTION",
      "name": "Wellfield Protection",
      "description": "Protection zones around potable water supply wells, prohibited activities within wellfield zones, contamination prevention measures, zone of influence",
      "primary_sections": ["24-43"]
    },
    {
      "id": "POTABLE_WATER_STANDARDS",
      "name": "Potable Water Standards",
      "description": "Drinking water quality requirements, water supply well regulation, domestic well systems, cross-connection control, water main standards",
      "primary_sections": ["24-43.2", "24-43.3"]
    },
    {
      "id": "SEPTIC_OSTDS",
      "name": "Septic System (OSTDS) Regulation",
      "description": "Onsite sewage treatment and disposal systems, septic tank standards, connection to public sewer requirements, abandonment procedures",
      "primary_sections": ["24-42.7", "24-43.4"]
    },
    {
      "id": "TREE_REMOVAL",
      "name": "Tree Removal & Replacement",
      "description": "Permits for tree removal and relocation, replacement requirements, specimen tree standards, natural forest community protection, tree trust fund",
      "primary_sections": ["24-49"]
    },
    {
      "id": "WETLANDS_MANGROVE",
      "name": "Wetlands & Mangrove Protection",
      "description": "Environmental permits for work in wetlands, mangrove trimming certification, mitigation requirements, wetland determination",
      "primary_sections": ["24-48"]
    },
    {
      "id": "AIR_QUALITY",
      "name": "Air Quality & Emissions",
      "description": "Prohibitions against air pollution, vehicle emission standards, open burning restrictions, sulfur dioxide limits, ozone-depleting compounds, asbestos spraying prohibition",
      "primary_sections": ["24-41"]
    },
    {
      "id": "UNDERGROUND_STORAGE",
      "name": "Underground Storage Tanks",
      "description": "Registration, monitoring, and closure requirements for underground storage facilities containing hazardous materials, tank abandonment procedures",
      "primary_sections": ["24-45"]
    },
    {
      "id": "ENVIRONMENTAL_PERMIT_PROCESS",
      "name": "Environmental Permit Process",
      "description": "Application procedures for environmental permits, evaluation factors, bonding requirements, permit issuance, transfer, suspension, revocation",
      "primary_sections": ["24-48", "24-48.1", "24-48.2", "24-48.3"]
    },
    {
      "id": "OPERATING_PERMITS",
      "name": "Operating Permits",
      "description": "Permits for operating wastewater treatment, water supply, or air pollution control facilities, competent supervision requirements",
      "primary_sections": ["24-18", "24-19"]
    },
    {
      "id": "PLAN_APPROVAL",
      "name": "Plan Approval & Engineering",
      "description": "Requirements for plan approval before construction, licensed engineer requirements, technical report standards, standards for preparation of plans",
      "primary_sections": ["24-15"]
    },
    {
      "id": "PENALTIES_LIABILITY",
      "name": "Penalties & Civil Liability",
      "description": "Criminal penalties for environmental violations, civil liability, joint and several liability, attorney fees, penalty amounts per day and per violation",
      "primary_sections": ["24-30", "24-31"]
    },
    {
      "id": "ENFORCEMENT_ACTIONS",
      "name": "Enforcement Actions",
      "description": "Stop orders, injunctions, enforcement procedures, contempt powers, remedies for environmental violations",
      "primary_sections": ["24-9", "24-10", "24-29"]
    },
    {
      "id": "VARIANCES_EXTENSIONS",
      "name": "Variances & Extensions",
      "description": "Procedures for obtaining variances from environmental requirements, time extensions for compliance, conditions for granting variances",
      "primary_sections": ["24-12", "24-13"]
    },
    {
      "id": "SPILL_REPORTING",
      "name": "Spill & Abnormal Occurrence Reporting",
      "description": "Reporting requirements for abnormal occurrences, unauthorized discharges, spills of hazardous materials, emergency response procedures, notification timelines",
      "primary_sections": ["24-20"]
    },
    {
      "id": "SITE_REHABILITATION",
      "name": "Site Rehabilitation & Cleanup (CTLs)",
      "description": "Cleanup target levels for contaminated sites, site rehabilitation action procedures, compliance testing, sampling methods and points",
      "primary_sections": ["24-44"]
    },
    {
      "id": "BROWNFIELDS",
      "name": "Brownfields Redevelopment",
      "description": "Brownfields program adoption, rehabilitation incentives for contaminated properties, State coordination for brownfield designations",
      "primary_sections": ["24-26"]
    },
    {
      "id": "NUISANCE_ABATEMENT",
      "name": "Nuisance Abatement",
      "description": "Prohibition of nuisances, sanitary nuisances injurious to health, conditions constituting nuisance, abatement procedures",
      "primary_sections": ["24-27", "24-28"]
    },
    {
      "id": "LIQUID_WASTE_TRANSPORT",
      "name": "Liquid Waste Transport",
      "description": "Regulation of liquid waste transporters, vehicle and equipment requirements, approved disposal site requirements, manifesting",
      "primary_sections": ["24-46"]
    },
    {
      "id": "METAL_RECYCLING",
      "name": "Metal Recycling Facilities",
      "description": "Operating standards for metal recycling facilities, stormwater controls, containment requirements for recyclable materials",
      "primary_sections": ["24-47"]
    },
    {
      "id": "EQCB_ADMINISTRATION",
      "name": "EQCB Authority & Administration",
      "description": "Environmental Quality Control Board structure and powers, Department Director duties, appeals process, department organization, water control map",
      "primary_sections": ["24-6", "24-7", "24-8", "24-11"]
    },
    {
      "id": "BISCAYNE_BAY",
      "name": "Biscayne Bay Conservation",
      "description": "Aquatic park designation for Biscayne Bay, floating structure prohibitions, non-water-dependent structure restrictions, environmental enhancement trust fund",
      "primary_sections": ["24-48.22", "24-48.23", "24-48.24", "24-40"]
    },
    {
      "id": "EEL_PROGRAM",
      "name": "Environmentally Endangered Lands",
      "description": "EEL acquisition program, trust fund, land acquisition selection committee, management plans for environmentally endangered lands",
      "primary_sections": ["24-50"]
    },
    {
      "id": "CONSTRUCTION_APPROVAL",
      "name": "Construction Project Approval",
      "description": "Requirements for constructing wastewater, water supply, or air pollution control facilities, certificates of occupancy, facility construction standards",
      "primary_sections": ["24-16", "24-17"]
    },
    {
      "id": "FEES_BONDS_FUNDS",
      "name": "Fees, Bonds & Trust Funds",
      "description": "Service fees payable to County, collection procedures, refund policies, performance bond waivers, enforcement fund, pollution prevention fund, wetlands fund, tree trust fund",
      "primary_sections": ["24-32", "24-33", "24-34", "24-35", "24-36", "24-37", "24-38", "24-39"]
    },
    {
      "id": "SEWER_INFRASTRUCTURE",
      "name": "Sewer System Infrastructure",
      "description": "Sanitary sewer collection and transmission system standards, tertiary treatment requirements, capacity certification, system evaluation surveys",
      "primary_sections": ["24-42.1", "24-42.2", "24-42.3"]
    },
    {
      "id": "WATER_SEWER_SERVICE",
      "name": "Water & Sewer Service Approval",
      "description": "Statements of approved water or sewer service, emergency rate requests, feasible distance for public water mains and sanitary sewers",
      "primary_sections": ["24-14", "24-43.4"]
    },
    {
      "id": "COASTAL_ENVIRONMENTAL_IMPACT",
      "name": "Coastal & Environmental Impact",
      "description": "Comprehensive environmental impact statements, coastal construction requirements, wetland basin plans, North Trail Basin, Bird Drive Everglades",
      "primary_sections": ["24-48.15", "24-48.20", "24-48.21"]
    }
  ]
}
```

Save this as `concepts.json` in the repository root before running the pipeline.
