// ============================================================
// BATCH 01 — Scope & Rules (Sec. 24-1 through 24-4)
// Miami-Dade County Chapter 24 — Environmental Protection
// ============================================================

// ------------------------------
// CONSTRAINTS (run once)
// ------------------------------

CREATE CONSTRAINT IF NOT EXISTS FOR (s:Section) REQUIRE s.number IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (r:Requirement) REQUIRE r.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (t:Threshold) REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (ro:Role) REQUIRE ro.name IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (p:Process) REQUIRE p.name IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (pe:Penalty) REQUIRE pe.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (pl:Place) REQUIRE pl.name IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (a:Activity) REQUIRE a.name IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (d:Definition) REQUIRE d.term IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (st:Standard) REQUIRE st.name IS UNIQUE;

// ============================================================
// SECTION NODES
// ============================================================

MERGE (s:Section {number: '24-1'})
SET s.title = 'Short title',
    s.full_text = 'This chapter enacted under and pursuant to the provisions of the Home Rule Charter of Government for Miami-Dade County, Florida, shall be known and may be cited as the "Miami-Dade County Environmental Protection Ordinance."',
    s.parent_section = '24';

MERGE (s:Section {number: '24-2'})
SET s.title = 'Declaration of legislative intent',
    s.full_text = 'The Board finds and determines that the reasonable control and regulation of activities which are causing or may cause pollution or contamination of air, water, soil and property is required for the protection and preservation of the public health, safety and welfare. It is the intent and purpose of this chapter to provide and maintain for the citizens and visitors of Miami-Dade County standards which will insure the purity of all waters consistent with public health and public enjoyment thereof, the propagation and protection of wildlife, birds, game, fish and other aquatic life, and atmospheric purity and freedom of the air from contaminants of synergistic agents injurious to human, plant or animal life, or property, or which unreasonably interfere with the comfortable enjoyment of life or property, or the conduct of business. The Board finds it necessary to establish, within the unincorporated and incorporated areas of Miami-Dade County, Countywide water control, coastal engineering, and coastal wetlands management programs for the purpose of maintaining adequate water levels, flood control, drainage, water conservation, and prevention of saltwater intrusion; for preserving beaches and shorelines; for managing coastal wetland resources; for acquisition of lands by gift, donation, purchase, condemnation or otherwise, as necessary for such programs; and providing for cooperation with federal, State and local agencies and authorities. The Board further finds it necessary to maintain within Miami-Dade County a freshwater wetlands management program for the purposes of providing adequate water levels, flood control, water conservation, protection of water quality and recharge to the Biscayne Aquifer, and prevention of saltwater intrusion; for the maintenance of the biological integrity of freshwater wetlands in Miami-Dade County; for the protection of the interrelated natural functions between Miami-Dade County\'s wetlands and the natural systems in Everglades National Park; for managing freshwater wetland resources in accordance with environmental standards and management criteria as recommended by the Miami-Dade County Comprehensive Development Master Plan and Chapter 33B of the Code of Miami-Dade County, Florida, as amended from time to time; and providing for cooperation with federal, State, and local agencies and authorities. The Board finds it necessary to establish for Miami-Dade County a Tree and Forest Resources Program for the purpose of protecting, preserving and replacing tree canopy, preserving natural forest communities including associated understory, providing protection for specimen-size trees and environmentally-sensitive tree resources, conserving rare, endangered, threatened and endemic species, protecting historically-significant tree resources, promoting the preservation of subtropical vegetation and unique or unusual species, providing for wildlife habitat, maintaining the natural character of neighborhoods, preserving the natural diversity of species, promoting environmentally-sound aesthetics, and providing for improved environmental quality by recognizing the numerous beneficial effects of trees. This program shall be a minimum standard and shall apply to both the incorporated and unincorporated areas, and in the unincorporated areas shall be enforced by the Department of Environmental Resources Management, and in the incorporated areas shall be enforced by the municipalities, unless the County is notified by a municipality, in the form of a letter from an official of the municipality or by resolution, that the municipality desires the County to enforce the Miami-Dade County Tree and Forest Program within the municipality. Any municipality may establish and enforce its own ordinance provided such ordinance is equivalent to or more stringent than the provisions of Ordinance Number 89-8. The provisions of this chapter are not intended and shall not be construed as superseding or conflicting with any statutory provisions relating to, or rules and regulations promulgated by, the Florida State Department of Environmental Protection, but shall be construed as implementing and assisting the enforcement thereof. It is not the intent of this Board to hereby preempt the authority of any municipality in the exercise of its authority to issue coastal construction permits or to restrict it from adopting more stringent standards, the purpose of this chapter being to establish minimum standards for the issuance of coastal construction permits within all of Miami-Dade County.',
    s.parent_section = '24';

MERGE (s:Section {number: '24-3'})
SET s.title = 'Rules and regulations',
    s.full_text = 'The Board of County Commissioners shall adopt, revise, and amend from time to time appropriate rules and regulations reasonably necessary for the implementation and effective enforcement, administration and interpretation of the provisions of this chapter, and to provide for the effective and continuing control and regulation of air and water pollution in this County within the framework of this chapter. No such rules and regulations, including amendments thereto, shall be adopted or become effective until after a public hearing has been held by the Board of County Commissioners pursuant to notice published at least ten (10) days prior to the hearing. When adopted by the Board of County Commissioners and filed with the clerk, such rules and regulations shall have force and effect of law.',
    s.parent_section = '24';

MERGE (s:Section {number: '24-4'})
SET s.title = 'Application of chapter and time for compliance',
    s.full_text = '(1) New facilities. On and after the effective date of this chapter, any person installing, constructing, or placing in operation for the first time any facility, equipment or process, the use of which will or may cause, or reasonably tend to cause, any air or water pollution as defined and controlled by this chapter, or who shall undertake the alterations, reconstruction or extension of existing facilities, equipment or processes in such a substantial manner as to materially increase the level or amount of air or water pollution, shall be subject to and required to comply with all the provisions of this chapter. (2) Existing facilities. All facilities, equipment, plants and projects that are in actual use and operation on the effective date of this chapter shall have until and including January 1, 1968, to fully comply with and conform to the requirements of this chapter, provided that all existing facilities shall comply with, and shall not commit violations of, the following provisions of this chapter after January 1, 1964, namely: Section 24-5 (Nuisance); Section 24-42 (Toxic waste discharges); Section 24-41 (Black smoke emissions); Section 24-41.4 (Open burning); and Section 24-41.9 (Reduction of animal matter). (3) Intent. It is intended that the provisions of this chapter shall be applicable to all new facilities and to any major or substantial addition, enlargement or extension of existing facilities; that existing facilities shall have until January 1, 1965, to comply with the specific sections of this chapter enumerated in subsection (2) hereinabove; and that existing facilities shall have until January 1, 1968, to comply with all other sections or provisions of this chapter (except those specifically designated in subsection (2) hereof), subject only to variances or extensions of time for compliance granted pursuant to the provisions of this chapter. (4) Replacements. The replacement with identical or similar parts and minor changes that do not affect the character of the waste discharge or emission of air contaminants, or do not materially increase the existing amount of air or water pollution, shall not be considered as constituting the alteration, reconstruction or extension of an existing facility, but shall be considered as constituting an existing facility, for the purpose of this chapter.',
    s.parent_section = '24';

// Parent chapter node
MERGE (s:Section {number: '24'})
SET s.title = 'Environmental Protection',
    s.full_text = 'Miami-Dade County Environmental Protection Ordinance — Chapter 24',
    s.parent_section = '';

// ============================================================
// REQUIREMENT NODES
// ============================================================

// --- From Sec. 24-2 ---

MERGE (r:Requirement {id: 'REQ-24-2-001'})
SET r.text = 'This program shall be a minimum standard and shall apply to both the incorporated and unincorporated areas, and in the unincorporated areas shall be enforced by the Department of Environmental Resources Management, and in the incorporated areas shall be enforced by the municipalities, unless the County is notified by a municipality, in the form of a letter from an official of the municipality or by resolution, that the municipality desires the County to enforce the Miami-Dade County Tree and Forest Program within the municipality.',
    r.type = 'obligation',
    r.condition = 'Tree and Forest Resources Program',
    r.section_ref = '24-2';

MERGE (r:Requirement {id: 'REQ-24-2-002'})
SET r.text = 'Any municipality may establish and enforce its own ordinance provided such ordinance is equivalent to or more stringent than the provisions of Ordinance Number 89-8.',
    r.type = 'permission',
    r.condition = 'municipality tree ordinance must be equivalent to or more stringent than Ordinance 89-8',
    r.section_ref = '24-2';

MERGE (r:Requirement {id: 'REQ-24-2-003'})
SET r.text = 'The provisions of this chapter are not intended and shall not be construed as superseding or conflicting with any statutory provisions relating to, or rules and regulations promulgated by, the Florida State Department of Environmental Protection, but shall be construed as implementing and assisting the enforcement thereof.',
    r.type = 'prohibition',
    r.condition = 'interpretation of chapter relative to state DEP authority',
    r.section_ref = '24-2';

MERGE (r:Requirement {id: 'REQ-24-2-004'})
SET r.text = 'It is not the intent of this Board to hereby preempt the authority of any municipality in the exercise of its authority to issue coastal construction permits or to restrict it from adopting more stringent standards, the purpose of this chapter being to establish minimum standards for the issuance of coastal construction permits within all of Miami-Dade County.',
    r.type = 'permission',
    r.condition = 'municipal authority over coastal construction permits',
    r.section_ref = '24-2';

// --- From Sec. 24-3 ---

MERGE (r:Requirement {id: 'REQ-24-3-001'})
SET r.text = 'The Board of County Commissioners shall adopt, revise, and amend from time to time appropriate rules and regulations reasonably necessary for the implementation and effective enforcement, administration and interpretation of the provisions of this chapter, and to provide for the effective and continuing control and regulation of air and water pollution in this County within the framework of this chapter.',
    r.type = 'obligation',
    r.condition = '',
    r.section_ref = '24-3';

MERGE (r:Requirement {id: 'REQ-24-3-002'})
SET r.text = 'No such rules and regulations, including amendments thereto, shall be adopted or become effective until after a public hearing has been held by the Board of County Commissioners pursuant to notice published at least ten (10) days prior to the hearing.',
    r.type = 'prohibition',
    r.condition = 'adoption of rules and regulations',
    r.section_ref = '24-3';

MERGE (r:Requirement {id: 'REQ-24-3-003'})
SET r.text = 'When adopted by the Board of County Commissioners and filed with the clerk, such rules and regulations shall have force and effect of law.',
    r.type = 'obligation',
    r.condition = 'rules adopted and filed with clerk',
    r.section_ref = '24-3';

// --- From Sec. 24-4 ---

MERGE (r:Requirement {id: 'REQ-24-4-001'})
SET r.text = 'On and after the effective date of this chapter, any person installing, constructing, or placing in operation for the first time any facility, equipment or process, the use of which will or may cause, or reasonably tend to cause, any air or water pollution as defined and controlled by this chapter, or who shall undertake the alterations, reconstruction or extension of existing facilities, equipment or processes in such a substantial manner as to materially increase the level or amount of air or water pollution, shall be subject to and required to comply with all the provisions of this chapter.',
    r.type = 'obligation',
    r.condition = 'new facilities or substantial alterations to existing facilities',
    r.section_ref = '24-4';

MERGE (r:Requirement {id: 'REQ-24-4-002'})
SET r.text = 'All facilities, equipment, plants and projects that are in actual use and operation on the effective date of this chapter shall have until and including January 1, 1968, to fully comply with and conform to the requirements of this chapter.',
    r.type = 'obligation',
    r.condition = 'existing facilities in operation on effective date',
    r.section_ref = '24-4';

MERGE (r:Requirement {id: 'REQ-24-4-003'})
SET r.text = 'all existing facilities shall comply with, and shall not commit violations of, the following provisions of this chapter after January 1, 1964, namely: Section 24-5 (Nuisance); Section 24-42 (Toxic waste discharges); Section 24-41 (Black smoke emissions); Section 24-41.4 (Open burning); and Section 24-41.9 (Reduction of animal matter).',
    r.type = 'obligation',
    r.condition = 'existing facilities — early compliance sections',
    r.section_ref = '24-4';

MERGE (r:Requirement {id: 'REQ-24-4-004'})
SET r.text = 'existing facilities shall have until January 1, 1965, to comply with the specific sections of this chapter enumerated in subsection (2) hereinabove; and that existing facilities shall have until January 1, 1968, to comply with all other sections or provisions of this chapter (except those specifically designated in subsection (2) hereof), subject only to variances or extensions of time for compliance granted pursuant to the provisions of this chapter.',
    r.type = 'obligation',
    r.condition = 'existing facilities — phased compliance timeline',
    r.section_ref = '24-4';

MERGE (r:Requirement {id: 'REQ-24-4-005'})
SET r.text = 'The replacement with identical or similar parts and minor changes that do not affect the character of the waste discharge or emission of air contaminants, or do not materially increase the existing amount of air or water pollution, shall not be considered as constituting the alteration, reconstruction or extension of an existing facility, but shall be considered as constituting an existing facility, for the purpose of this chapter.',
    r.type = 'permission',
    r.condition = 'replacement with identical/similar parts or minor changes',
    r.section_ref = '24-4';

// ============================================================
// THRESHOLD NODES
// ============================================================

MERGE (t:Threshold {id: 'THR-24-3-001'})
SET t.value = '10',
    t.unit = 'days',
    t.parameter = 'public notice period before hearing',
    t.direction = 'min',
    t.context = 'Notice must be published at least 10 days prior to public hearing for adoption of rules and regulations';

MERGE (t:Threshold {id: 'THR-24-4-001'})
SET t.value = 'January 1, 1968',
    t.unit = 'date',
    t.parameter = 'compliance deadline for existing facilities',
    t.direction = 'max',
    t.context = 'All existing facilities must fully comply with all chapter provisions by this date';

MERGE (t:Threshold {id: 'THR-24-4-002'})
SET t.value = 'January 1, 1964',
    t.unit = 'date',
    t.parameter = 'early compliance deadline for specific sections',
    t.direction = 'max',
    t.context = 'Existing facilities must comply with Sec. 24-5 (Nuisance), 24-42 (Toxic waste), 24-41 (Black smoke), 24-41.4 (Open burning), 24-41.9 (Animal matter) after this date';

MERGE (t:Threshold {id: 'THR-24-4-003'})
SET t.value = 'January 1, 1965',
    t.unit = 'date',
    t.parameter = 'compliance deadline for enumerated sections',
    t.direction = 'max',
    t.context = 'Existing facilities must comply with sections enumerated in Sec. 24-4(2) by this date';

// ============================================================
// ROLE NODES
// ============================================================

MERGE (ro:Role {name: 'Board of County Commissioners'})
SET ro.authority_level = 'regulator',
    ro.defined_in = '24-2';

MERGE (ro:Role {name: 'Department of Environmental Resources Management'})
SET ro.authority_level = 'regulator',
    ro.defined_in = '24-2';

MERGE (ro:Role {name: 'Municipality'})
SET ro.authority_level = 'regulator',
    ro.defined_in = '24-2';

MERGE (ro:Role {name: 'Florida State Department of Environmental Protection'})
SET ro.authority_level = 'regulator',
    ro.defined_in = '24-2';

MERGE (ro:Role {name: 'Clerk'})
SET ro.authority_level = 'regulator',
    ro.defined_in = '24-3';

MERGE (ro:Role {name: 'Person'})
SET ro.authority_level = 'regulated',
    ro.defined_in = '24-4';

MERGE (ro:Role {name: 'Facility Operator'})
SET ro.authority_level = 'regulated',
    ro.defined_in = '24-4';

// ============================================================
// PROCESS NODES
// ============================================================

MERGE (p:Process {name: 'Rules and Regulations Adoption'})
SET p.steps = '1. Board of County Commissioners drafts rules and regulations. 2. Public notice published at least 10 days prior to hearing. 3. Public hearing held by Board of County Commissioners. 4. Rules adopted by Board and filed with the clerk. 5. Rules have force and effect of law.',
    p.timeframe = '10 days minimum notice before hearing',
    p.section_ref = '24-3';

// ============================================================
// PLACE NODES
// ============================================================

MERGE (pl:Place {name: 'Miami-Dade County'})
SET pl.type = 'area',
    pl.geographic_scope = 'Incorporated and unincorporated areas of Miami-Dade County, Florida';

MERGE (pl:Place {name: 'Everglades National Park'})
SET pl.type = 'area',
    pl.geographic_scope = 'Federal national park adjacent to Miami-Dade County with interrelated natural functions to county wetlands';

MERGE (pl:Place {name: 'Biscayne Aquifer'})
SET pl.type = 'waterway',
    pl.geographic_scope = 'Underground aquifer beneath Miami-Dade County; primary source of potable water; recharge protected by freshwater wetlands';

// ============================================================
// ACTIVITY NODES
// ============================================================

MERGE (a:Activity {name: 'Installing or constructing new facility'})
SET a.category = 'construction',
    a.requires_permit = true,
    a.section_ref = '24-4';

MERGE (a:Activity {name: 'Alteration or extension of existing facility'})
SET a.category = 'construction',
    a.requires_permit = true,
    a.section_ref = '24-4';

MERGE (a:Activity {name: 'Water control and coastal engineering'})
SET a.category = 'land_use',
    a.requires_permit = true,
    a.section_ref = '24-2';

MERGE (a:Activity {name: 'Coastal wetlands management'})
SET a.category = 'land_use',
    a.requires_permit = true,
    a.section_ref = '24-2';

MERGE (a:Activity {name: 'Freshwater wetlands management'})
SET a.category = 'land_use',
    a.requires_permit = true,
    a.section_ref = '24-2';

MERGE (a:Activity {name: 'Tree and forest resources management'})
SET a.category = 'land_use',
    a.requires_permit = true,
    a.section_ref = '24-2';

MERGE (a:Activity {name: 'Coastal construction'})
SET a.category = 'construction',
    a.requires_permit = true,
    a.section_ref = '24-2';

// ============================================================
// STANDARD NODES
// ============================================================

MERGE (st:Standard {name: 'Home Rule Charter of Government for Miami-Dade County'})
SET st.external_ref = 'Home Rule Charter of Government for Miami-Dade County, Florida',
    st.type = 'local';

MERGE (st:Standard {name: 'Chapter 33B of the Code of Miami-Dade County'})
SET st.external_ref = 'Chapter 33B of the Code of Miami-Dade County, Florida',
    st.type = 'local';

MERGE (st:Standard {name: 'Ordinance Number 89-8'})
SET st.external_ref = 'Miami-Dade County Ordinance Number 89-8 — Tree and Forest Resources',
    st.type = 'local';

MERGE (st:Standard {name: 'Miami-Dade County Comprehensive Development Master Plan'})
SET st.external_ref = 'Miami-Dade County Comprehensive Development Master Plan',
    st.type = 'local';

// ============================================================
// RELATIONSHIPS — PART_OF (Section hierarchy)
// ============================================================

MATCH (child:Section {number: '24-1'})
MATCH (parent:Section {number: '24'})
MERGE (child)-[:PART_OF]->(parent);

MATCH (child:Section {number: '24-2'})
MATCH (parent:Section {number: '24'})
MERGE (child)-[:PART_OF]->(parent);

MATCH (child:Section {number: '24-3'})
MATCH (parent:Section {number: '24'})
MERGE (child)-[:PART_OF]->(parent);

MATCH (child:Section {number: '24-4'})
MATCH (parent:Section {number: '24'})
MERGE (child)-[:PART_OF]->(parent);

// ============================================================
// RELATIONSHIPS — CONTAINS (Section -> Requirement)
// ============================================================

MATCH (s:Section {number: '24-2'})
MATCH (r:Requirement {id: 'REQ-24-2-001'})
MERGE (s)-[:CONTAINS]->(r);

MATCH (s:Section {number: '24-2'})
MATCH (r:Requirement {id: 'REQ-24-2-002'})
MERGE (s)-[:CONTAINS]->(r);

MATCH (s:Section {number: '24-2'})
MATCH (r:Requirement {id: 'REQ-24-2-003'})
MERGE (s)-[:CONTAINS]->(r);

MATCH (s:Section {number: '24-2'})
MATCH (r:Requirement {id: 'REQ-24-2-004'})
MERGE (s)-[:CONTAINS]->(r);

MATCH (s:Section {number: '24-3'})
MATCH (r:Requirement {id: 'REQ-24-3-001'})
MERGE (s)-[:CONTAINS]->(r);

MATCH (s:Section {number: '24-3'})
MATCH (r:Requirement {id: 'REQ-24-3-002'})
MERGE (s)-[:CONTAINS]->(r);

MATCH (s:Section {number: '24-3'})
MATCH (r:Requirement {id: 'REQ-24-3-003'})
MERGE (s)-[:CONTAINS]->(r);

MATCH (s:Section {number: '24-4'})
MATCH (r:Requirement {id: 'REQ-24-4-001'})
MERGE (s)-[:CONTAINS]->(r);

MATCH (s:Section {number: '24-4'})
MATCH (r:Requirement {id: 'REQ-24-4-002'})
MERGE (s)-[:CONTAINS]->(r);

MATCH (s:Section {number: '24-4'})
MATCH (r:Requirement {id: 'REQ-24-4-003'})
MERGE (s)-[:CONTAINS]->(r);

MATCH (s:Section {number: '24-4'})
MATCH (r:Requirement {id: 'REQ-24-4-004'})
MERGE (s)-[:CONTAINS]->(r);

MATCH (s:Section {number: '24-4'})
MATCH (r:Requirement {id: 'REQ-24-4-005'})
MERGE (s)-[:CONTAINS]->(r);

// ============================================================
// RELATIONSHIPS — CONTAINS (Section -> Process)
// ============================================================

MATCH (s:Section {number: '24-3'})
MATCH (p:Process {name: 'Rules and Regulations Adoption'})
MERGE (s)-[:CONTAINS]->(p);

// ============================================================
// RELATIONSHIPS — HAS_THRESHOLD (Requirement -> Threshold)
// ============================================================

MATCH (r:Requirement {id: 'REQ-24-3-002'})
MATCH (t:Threshold {id: 'THR-24-3-001'})
MERGE (r)-[:HAS_THRESHOLD]->(t);

MATCH (r:Requirement {id: 'REQ-24-4-002'})
MATCH (t:Threshold {id: 'THR-24-4-001'})
MERGE (r)-[:HAS_THRESHOLD]->(t);

MATCH (r:Requirement {id: 'REQ-24-4-003'})
MATCH (t:Threshold {id: 'THR-24-4-002'})
MERGE (r)-[:HAS_THRESHOLD]->(t);

MATCH (r:Requirement {id: 'REQ-24-4-004'})
MATCH (t:Threshold {id: 'THR-24-4-003'})
MERGE (r)-[:HAS_THRESHOLD]->(t);

// Link REQ-24-4-004 also to the 1968 deadline
MATCH (r:Requirement {id: 'REQ-24-4-004'})
MATCH (t:Threshold {id: 'THR-24-4-001'})
MERGE (r)-[:HAS_THRESHOLD]->(t);

// ============================================================
// RELATIONSHIPS — ENFORCED_BY (Requirement -> Role)
// ============================================================

MATCH (r:Requirement {id: 'REQ-24-2-001'})
MATCH (ro:Role {name: 'Department of Environmental Resources Management'})
MERGE (r)-[:ENFORCED_BY]->(ro);

MATCH (r:Requirement {id: 'REQ-24-2-001'})
MATCH (ro:Role {name: 'Municipality'})
MERGE (r)-[:ENFORCED_BY]->(ro);

MATCH (r:Requirement {id: 'REQ-24-3-001'})
MATCH (ro:Role {name: 'Board of County Commissioners'})
MERGE (r)-[:ENFORCED_BY]->(ro);

MATCH (r:Requirement {id: 'REQ-24-3-002'})
MATCH (ro:Role {name: 'Board of County Commissioners'})
MERGE (r)-[:ENFORCED_BY]->(ro);

MATCH (r:Requirement {id: 'REQ-24-3-003'})
MATCH (ro:Role {name: 'Board of County Commissioners'})
MERGE (r)-[:ENFORCED_BY]->(ro);

MATCH (r:Requirement {id: 'REQ-24-3-003'})
MATCH (ro:Role {name: 'Clerk'})
MERGE (r)-[:ENFORCED_BY]->(ro);

// ============================================================
// RELATIONSHIPS — APPLIES_TO (Requirement -> Role/Activity/Place)
// ============================================================

// REQ-24-2-001 applies to Tree and Forest Resources Program activities
MATCH (r:Requirement {id: 'REQ-24-2-001'})
MATCH (a:Activity {name: 'Tree and forest resources management'})
MERGE (r)-[:APPLIES_TO]->(a);

// REQ-24-2-001 applies to Miami-Dade County
MATCH (r:Requirement {id: 'REQ-24-2-001'})
MATCH (pl:Place {name: 'Miami-Dade County'})
MERGE (r)-[:APPLIES_TO]->(pl);

// REQ-24-2-002 applies to Municipality role
MATCH (r:Requirement {id: 'REQ-24-2-002'})
MATCH (ro:Role {name: 'Municipality'})
MERGE (r)-[:APPLIES_TO]->(ro);

// REQ-24-2-003 applies to Florida DEP relationship
MATCH (r:Requirement {id: 'REQ-24-2-003'})
MATCH (ro:Role {name: 'Florida State Department of Environmental Protection'})
MERGE (r)-[:APPLIES_TO]->(ro);

// REQ-24-2-004 applies to coastal construction and municipalities
MATCH (r:Requirement {id: 'REQ-24-2-004'})
MATCH (a:Activity {name: 'Coastal construction'})
MERGE (r)-[:APPLIES_TO]->(a);

MATCH (r:Requirement {id: 'REQ-24-2-004'})
MATCH (ro:Role {name: 'Municipality'})
MERGE (r)-[:APPLIES_TO]->(ro);

// REQ-24-4-001 applies to Person and new/altered facilities
MATCH (r:Requirement {id: 'REQ-24-4-001'})
MATCH (ro:Role {name: 'Person'})
MERGE (r)-[:APPLIES_TO]->(ro);

MATCH (r:Requirement {id: 'REQ-24-4-001'})
MATCH (a:Activity {name: 'Installing or constructing new facility'})
MERGE (r)-[:APPLIES_TO]->(a);

MATCH (r:Requirement {id: 'REQ-24-4-001'})
MATCH (a:Activity {name: 'Alteration or extension of existing facility'})
MERGE (r)-[:APPLIES_TO]->(a);

// REQ-24-4-002 applies to Facility Operator
MATCH (r:Requirement {id: 'REQ-24-4-002'})
MATCH (ro:Role {name: 'Facility Operator'})
MERGE (r)-[:APPLIES_TO]->(ro);

// REQ-24-4-003 applies to Facility Operator
MATCH (r:Requirement {id: 'REQ-24-4-003'})
MATCH (ro:Role {name: 'Facility Operator'})
MERGE (r)-[:APPLIES_TO]->(ro);

// REQ-24-4-004 applies to Facility Operator
MATCH (r:Requirement {id: 'REQ-24-4-004'})
MATCH (ro:Role {name: 'Facility Operator'})
MERGE (r)-[:APPLIES_TO]->(ro);

// REQ-24-4-005 applies to Facility Operator
MATCH (r:Requirement {id: 'REQ-24-4-005'})
MATCH (ro:Role {name: 'Facility Operator'})
MERGE (r)-[:APPLIES_TO]->(ro);

// ============================================================
// RELATIONSHIPS — REFERENCES_STANDARD (Requirement -> Standard)
// ============================================================

MATCH (r:Requirement {id: 'REQ-24-2-002'})
MATCH (st:Standard {name: 'Ordinance Number 89-8'})
MERGE (r)-[:REFERENCES_STANDARD]->(st);

// ============================================================
// RELATIONSHIPS — REFERENCES (Section -> Section cross-refs)
// ============================================================

// Sec. 24-2 references Chapter 33B
// (Chapter 33B is external — captured as Standard node above)

// Sec. 24-4 references Sec. 24-5 (Nuisance)
MERGE (ref_s:Section {number: '24-5'})
ON CREATE SET ref_s.title = 'Definitions', ref_s.full_text = '', ref_s.parent_section = '24';

MATCH (s:Section {number: '24-4'})
MATCH (ref:Section {number: '24-5'})
MERGE (s)-[:REFERENCES]->(ref);

// Sec. 24-4 references Sec. 24-42 (Toxic waste discharges)
MERGE (ref_s:Section {number: '24-42'})
ON CREATE SET ref_s.title = 'Prohibitions against water pollution', ref_s.full_text = '', ref_s.parent_section = '24';

MATCH (s:Section {number: '24-4'})
MATCH (ref:Section {number: '24-42'})
MERGE (s)-[:REFERENCES]->(ref);

// Sec. 24-4 references Sec. 24-41 (Black smoke emissions)
MERGE (ref_s:Section {number: '24-41'})
ON CREATE SET ref_s.title = 'Prohibitions against air pollution', ref_s.full_text = '', ref_s.parent_section = '24';

MATCH (s:Section {number: '24-4'})
MATCH (ref:Section {number: '24-41'})
MERGE (s)-[:REFERENCES]->(ref);

// Sec. 24-4 references Sec. 24-41.4 (Open burning)
MERGE (ref_s:Section {number: '24-41.4'})
ON CREATE SET ref_s.title = 'Open burning', ref_s.full_text = '', ref_s.parent_section = '24-41';

MATCH (s:Section {number: '24-4'})
MATCH (ref:Section {number: '24-41.4'})
MERGE (s)-[:REFERENCES]->(ref);

// Sec. 24-4 references Sec. 24-41.9 (Reduction of animal matter)
MERGE (ref_s:Section {number: '24-41.9'})
ON CREATE SET ref_s.title = 'Reduction of animal matter', ref_s.full_text = '', ref_s.parent_section = '24-41';

MATCH (s:Section {number: '24-4'})
MATCH (ref:Section {number: '24-41.9'})
MERGE (s)-[:REFERENCES]->(ref);

// ============================================================
// END OF BATCH 01
// ============================================================
