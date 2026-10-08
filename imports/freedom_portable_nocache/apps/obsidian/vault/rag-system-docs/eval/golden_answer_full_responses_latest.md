# Golden Answer Full Responses (Latest)

Generated: 2026-08-19T11:28:44Z
Total queries: 22
Empty answers: 0

## 1. What logic exists in wf_0000_eintr_lmt_load_confirmation.XML?

- id: ans_001
- strategy: llm_primary
- llm_used: True
- llm_error: None
- answer_chars: 1050
- elapsed_sec: 21.3

### Ground Truth

wf_0000_eintr_lmt_load_confirmation.XML includes logic across source, transformation, and target steps. Notable entities include SQ_FactInteractionGrpActivity, FactInteractionGrpActivity, LMT_Load_confirmation.

### Answer

- The mapping loads target LMT_Load_confirmation, which has two fields: Source_Cd and Transaction_Ts [wf_0000_eintr_lmt_load_confirmation.XML:TARGET:LMT_Load_confirmation:40337486].

- The Source Qualifier SQ_FactInteractionGrpActivity uses an SQL override that selects source_cd and the maximum Transaction_ts grouped by source_cd from two sources, unioned: 
  "SEL source_cd, MAX(Transaction_ts) FROM fnd_eintr_db.FactInteractionGrpActivity GROUP BY 1 UNION SEL source_cd, MAX(Transaction_ts) FROM FND_EINTR_DB.InteractionStatus GROUP BY 1" [wf_0000_eintr_lmt_load_confirmation.XML:TRANSFORMATION:SQ_FactInteractionGrpActivity:b9030ea2].

- The SQ output ports map Source_Cd and Transaction_Ts into the target LMT_Load_confirmation.Source_Cd and LMT_Load_confirmation.Transaction_Ts respectively (lineage shows the target fields come from the SQ/Facts sources) [wf_0000_eintr_lmt_load_confirmation.XML:LINEAGE:LMT_Load_confirmation:Source_Cd:7e93f825] [wf_0000_eintr_lmt_load_confirmation.XML:LINEAGE:LMT_Load_confirmation:Transaction_Ts:daff17e6].

---

## 2. Find SQL override in wf_0000_eintr_lmt_load_confirmation.XML

- id: ans_003
- strategy: llm_primary
- llm_used: True
- llm_error: None
- answer_chars: 346
- elapsed_sec: 5.82

### Ground Truth

wf_0000_eintr_lmt_load_confirmation.XML contains Source Qualifier SQL override logic, including SQ_FactInteractionGrpActivity.

### Answer

The SQL override (in transformation SQ_FactInteractionGrpActivity) is:

SEL source_cd, MAX(Transaction_ts) FROM fnd_eintr_db.FactInteractionGrpActivity GROUP BY 1 UNION SEL source_cd, MAX(Transaction_ts) FROM FND_EINTR_DB.InteractionStatus GROUP BY 1 [wf_0000_eintr_lmt_load_confirmation.XML:TRANSFORMATION:SQ_FactInteractionGrpActivity:b9030ea2]

---

## 3. What logic exists in wf_4201_calculate_interaction_facts.XML?

- id: ans_005
- strategy: grounded_relevance_fallback
- llm_used: True
- llm_error: None
- answer_chars: 1369
- elapsed_sec: 44.0

### Ground Truth

wf_4201_calculate_interaction_facts.XML includes logic across source, transformation, and target steps. Notable entities include SQ_wk_hhldbusinessgeneration_vw, sq_sql_override_householdbusskey_id_interaction_event, InteractionGroupStatus.

### Answer

Based on retrieved Informatica evidence, logic in wf_4201_calculate_interaction_facts.xml appears in these nodes:
- LINEAGE: FactlessInteractionEvent.BaseInteractionGroup_Id (wf_4201_calculate_interaction_facts.XML) -> FILE: wf_4201_calculate_interaction_facts.XML NODE_CLASS: LINEAGE MAPPING: m_4201_wk_hhldbusinessgeneration_nb FOLDER: srctgt_EINTERACTION TARGET: FactlessInteractionEvent.BaseInteractionGroup_Id SOURCE: BaseInteracti... [wf_4201_calculate_interaction_facts.XML:LINEAGE:FactlessInteractionEvent:BaseInteractionGroup_Id:6747aa84]
- TRANSFORMATION: lkp_xref_xt (wf_4201_calculate_interaction_facts.XML) -> FILE: wf_4201_calculate_interaction_facts.XML NODE_CLASS: TRANSFORMATION NAME: lkp_xref_xt TYPE: Lookup Procedure MAPPING: m_4201_fnd_interactiongroupstatus FOLDER: srctgt_EINTERACTION PORTS: (5 total) - TRANSLATIONRU... [wf_4201_calculate_interaction_facts.XML:TRANSFORMATION:lkp_xref_xt:19793a54]
- LINEAGE: FactlessInteractionEvent.InteractionGroupBusinessKey_Id (wf_4201_calculate_interaction_facts.XML) -> FILE: wf_4201_calculate_interaction_facts.XML NODE_CLASS: LINEAGE MAPPING: m_4201_wk_hhldbusinessgeneration_nb FOLDER: srctgt_EINTERACTION TARGET: FactlessInteractionEvent.InteractionGroupBusinessKey_Id SOURCE: BaseIn... [wf_4201_calculate_interaction_facts.XML:LINEAGE:FactlessInteractionEvent:InteractionGroupBusinessKey_Id:51337efe]

---

## 4. Find SQL override in wf_4201_calculate_interaction_facts.XML

- id: ans_007
- strategy: llm_relevancy_rewrite
- llm_used: True
- llm_error: None
- answer_chars: 612
- elapsed_sec: 55.69

### Ground Truth

wf_4201_calculate_interaction_facts.XML contains Source Qualifier SQL override logic, including sq_sql_override_householdbusskey_id_interaction_event.

### Answer

- A SQL override exists as a Source Qualifier named "SQ_SQL_Override_InteractionEvent" for mapping m_4201_wk_interactionevent in wf_4201_calculate_interaction_facts.XML [0e1edc3c#0].  
- The same "SQ_SQL_Override_InteractionEvent" appears for mapping m_4201_wklogicalexcludeleads in wf_4201_calculate_interaction_facts.XML [6795d9bf#0].  
- It also appears for mapping m_4201_wkhouseholdexcludeleads in wf_4201_calculate_interaction_facts.XML [0746a6f6#0].  
- A non-override Source Qualifier "SQ_InteractionEvent" (mapping m_4201_fnd_wkbusinesslogicalkey_id) is present separately in the same file [20972fa6#0].

---

## 5. Find lineage records in wf_4201_calculate_interaction_facts.XML

- id: ans_008
- strategy: llm_primary
- llm_used: True
- llm_error: None
- answer_chars: 2357
- elapsed_sec: 28.26

### Ground Truth

wf_4201_calculate_interaction_facts.XML has field-level lineage through CONNECTOR paths. Key fields include DispIntGrpId, PrecDispUserTermCd.

### Answer

The workflow XML contains the following lineage records (each line cites the evidence chunk):

- FactlessInteractionEvent.BaseInteractionGroup_Id — mapping m_4201_wk_hhldbusinessgeneration_nb, folder srctgt_EINTERACTION, SOURCE BaseInteractionGroup.BaseInteractionGroup_Id, HOP_COUNT 2, RESOLVED yes; PATH shows SQ_Override_IE_BIG_LI_BC_UA_IGS_PIE → FactlessInteractionEvent.BaseInteractionGroup_Id [wf_4201_calculate_interaction_facts.XML:LINEAGE:FactlessInteractionEvent:BaseInteractionGroup_Id:6747aa84].

- FactLeadActivity.BaseInteractionGroup_Id — mapping m_4201_wk_hhldbusinessgeneration_nb, folder srctgt_EINTERACTION, SOURCE BaseInteractionGroup.BaseInteractionGroup_Id, HOP_COUNT 18, RESOLVED yes; PATH begins with fltr_count_greate_0 → SQ_FactInteractionGrpActivity → FactInteractionGrpActivity → JNRTRANS → EXPTRANS … and continues to fil_to_get_records_with_seqit_in_IE_is_between_seqstartit_and_seqendit_in_BIG [wf_4201_calculate_interaction_facts.XML:LINEAGE:FactLeadActivity:BaseInteractionGroup_Id:132504a0].

- FactLeadActivity.BaseInteractionGroup_Id — mapping m_4201_wk_hhldbusinessgeneration_nb, folder srctgt_EINTERACTION, SOURCE BaseInteractionGroup.BaseInteractionGroup_Id, HOP_COUNT 17, RESOLVED yes; PATH similar to above through exp_transaction_ts_to_date and fil_to_get_records_with_seqit… [wf_4201_calculate_interaction_facts.XML:LINEAGE:FactLeadActivity:BaseInteractionGroup_Id:1de5081a].

- FactInteractionGrpActivity.BaseInteractionGroup_Id — mapping m_4201_wk_hhldbusinessgeneration_nb, folder srctgt_EINTERACTION, SOURCE BaseInteractionGroup.BaseInteractionGroup_Id, HOP_COUNT 10, RESOLVED yes; PATH includes fltr_containmatric → exp_factinteractiongrpactivity → exp_lkp_in_2 → lkp_BaseCampaign → jnr_baseinteractiongroup_and_interactionevent → SQ_BaseInteractionGroup → BaseInteractionGroup.BaseInteractionGroup_Id [wf_4201_calculate_interaction_facts.XML:LINEAGE:FactInteractionGrpActivity:BaseInteractionGroup_Id:41de940b].

- FactLeadActivity.BaseInteractionGroup_Id — mapping m_4201_wk_hhldbusinessgeneration_nb, folder srctgt_EINTERACTION, SOURCE BaseInteractionGroup.BaseInteractionGroup_Id, HOP_COUNT 16, RESOLVED yes; PATH similar to the FactLeadActivity chains via jnr_baseinteractiongroup_and_interactionevent … [wf_4201_calculate_interaction_facts.XML:LINEAGE:FactLeadActivity:BaseInteractionGroup_Id:99d97727].

---

## 6. What logic exists in wf_4202_fnd_rltinteraction.XML?

- id: ans_009
- strategy: llm_primary
- llm_used: True
- llm_error: None
- answer_chars: 1744
- elapsed_sec: 18.0

### Ground Truth

wf_4202_fnd_rltinteraction.XML includes logic across source, transformation, and target steps. Notable entities include SQ_Override_DateChain_RLTInteractionAgreement, SQ_RLTInteractionAgreement, PolicyIdReference_Work.

### Answer

The workflow contains mapping logic in m_4202_dt_chn_rltinteractionagreement (folder srctgt_EINTERACTION) that derives PolicyIdReference_Work fields from PolicyIdReference_Xt via an expression transformation (exp_to_derive_new_policy_nb) fed by a source qualifier (SQ_PolicyIdReference_Xt):

- Declaration_Nb for PolicyIdReference_Work is derived from PolicyIdReference_Xt.Declaration_Nb through exp_to_derive_new_policy_nb and SQ_PolicyIdReference_Xt [wf_4202_fnd_rltinteraction.XML:LINEAGE:PolicyIdReference_Work:Declaration_Nb:2346d8a8].

- PolicyEffective_Dt for PolicyIdReference_Work is derived from PolicyIdReference_Xt.PolicyEffective_Dt through exp_to_derive_new_policy_nb and SQ_PolicyIdReference_Xt [wf_4202_fnd_rltinteraction.XML:LINEAGE:PolicyIdReference_Work:PolicyEffective_Dt:a70fb131].

- Source_Cd for PolicyIdReference_Work is derived from PolicyIdReference_Xt.Source_Cd through exp_to_derive_new_policy_nb and SQ_PolicyIdReference_Xt [wf_4202_fnd_rltinteraction.XML:LINEAGE:PolicyIdReference_Work:Source_Cd:50a25bda].

- Policy_Nb for PolicyIdReference_Work is derived from PolicyIdReference_Xt.Policy_Nb through exp_to_derive_new_policy_nb and SQ_PolicyIdReference_Xt [wf_4202_fnd_rltinteraction.XML:LINEAGE:PolicyIdReference_Work:Policy_Nb:757e68b8].

- RLTInteractionAgreement.Policy_Id is produced by assigning a new policy id (exp_assign_row_number.New_Policy_Id), joining to get the max surrogate key (jnr_to_get_max_surrogate_key.New_Policy_Id), and sourcing New_Policy_Id from SQ_RLTInteractionAgreement; its lineage traces back to PolicyIdReference_Xt.Policy_Id via PolicyIdReference_Work.Policy_Id and exp_to_derive_new_policy_nb [wf_4202_fnd_rltinteraction.XML:LINEAGE:RLTInteractionAgreement:Policy_Id:053820cf].

---

## 7. Find SQL override in wf_4202_fnd_rltinteraction.XML

- id: ans_011
- strategy: llm_primary
- llm_used: True
- llm_error: None
- answer_chars: 1888
- elapsed_sec: 38.14

### Ground Truth

wf_4202_fnd_rltinteraction.XML contains Source Qualifier SQL override logic, including SQ_Override_DateChain_RLTInteractionAgreement.

### Answer

The file contains these SQL_OVERRIDE definitions:

- SQ_RLTInteractionAgreement (mapping m_4202_fnd_rltinteractionagreement_ins2): 
  "SELECT RltInteractionAgreement_Id, LoadEvent_Id FROM $$interaction_fnd_db.RltInteractionAgreement rlt WHERE LoadEvent_Id>=$$load_event_id" [5a06e467]

- SQ_RLTInteractionAgreement1 (mapping m_4202_fnd_rltinteractionagreement_ins99): 
  "SELECT RltInteractionAgreement_Id FROM $$interaction_fnd_db.RltInteractionAgreement rlt WHERE LoadEvent_Id=$$latest_loadevent_id" [25313203]

- SQ_RLTInteractionAgreement_ins99 (mapping m_4202_fnd_wk_rltnteractionagreement_work): 
  "SELECT Vir_Tbl.Interactiongroup_Id, Vir_Tbl.InteractionGroupKey_Cd, Vir_Tbl.EIntrPolicyKey_Cd, Vir_Tbl.Effective_Dt, Vir_Tbl.Transaction_Ts , Vir_Tbl.Sequence_It, $$latest_loadevent_id as LoadEvent_Id, Vir_Tbl.EintrSource_Cd, 'INS99' AS Instance_Nm FROM ( SELECT RLT.Interactiongroup_Id, RLT.InteractionGroupKey_Cd, RLT.EIntrPolicyKey_Cd, RLT.EintrSource_Cd, RLT.Effective_Dt, MAX(IE.Transaction_Ts) AS Transaction_Ts , MAX(IE.Sequence_It) AS Sequence_It, MAX(IE.LoadEvent_Id) AS Max_LoadEvent_Id FROM $$interaction_fnd_db.RltInteractionAgreement RLT INNER JOIN $$interaction_fnd_db.InteractionE..." [03813ef8]

- SQ_RLTInteractionAgreement (mapping m_4202_fnd_rltinteractionagreement_ins99): 
  "SELECT ROW_NUMBER() OVER( ORDER BY Vir_Tbl.InteractionGroup_Id,Vir_Tbl.Sequence_It ) AS NUMBER_SEQ, Vir_Tbl.Interactiongroup_Id, Vir_Tbl.InteractionGroupKey_Cd, Vir_Tbl.EIntrPolicyKey_Cd, Vir_Tbl.EintrSource_Cd, Vir_Tbl.Transaction_Ts , Vir_Tbl.Sequence_It, Vir_Tbl.EprodSource_Cd, Vir_Tbl.New_Policy_Id, 1 AS o_dummy FROM ( SELECT ie.Interactiongroup_Id, ie.InteractionGroupKey_Cd, ie.PolicyKey_Cd as EIntrPolicyKey_Cd, ie.Source_Cd as EintrSource_Cd, ie.Transaction_Ts , ie.Sequence_It, XT.Source_cd AS EprodSource_Cd, XT.Policy_Id AS New_Policy_Id FROM $$interactio..." [7a8f0187#0]

---

## 8. Find lineage records in wf_4202_fnd_rltinteraction.XML

- id: ans_012
- strategy: llm_primary
- llm_used: True
- llm_error: None
- answer_chars: 2758
- elapsed_sec: 29.35

### Ground Truth

wf_4202_fnd_rltinteraction.XML has field-level lineage through CONNECTOR paths. Key fields include RltInteractionAgreement_Id, InteractionGroup_Id.

### Answer

Found lineage records in wf_4202_fnd_rltinteraction.XML:

- RLTInteractionAgreement.Policy_Id — Mapping: m_4202_dt_chn_rltinteractionagreement; Folder: srctgt_EINTERACTION; Target: RLTInteractionAgreement.Policy_Id; Source: PolicyIdReference_Xt.Policy_Id; Hop count: 7; Resolved: yes; Path: RLTInteractionAgreement.Policy_Id → exp_assign_row_number.New_Policy_Id → jnr_to_get_max_surrogate_key.New_Policy_Id → SQ_RLTInteractionAgreement.New_Policy_Id → PolicyIdReference_Work.Policy_Id → exp_to_derive_new_policy_nb.Policy_Id → SQ_PolicyIdReference_Xt.Policy_Id → PolicyIdReference_Xt.Policy_Id [wf_4202_fnd_rltinteraction.XML:LINEAGE:RLTInteractionAgreement:Policy_Id:053820cf]

- PolicyIdReference_Work.Policy_Id — Mapping: m_4202_dt_chn_rltinteractionagreement; Folder: srctgt_EINTERACTION; Target: PolicyIdReference_Work.Policy_Id; Source: PolicyIdReference_Xt.Policy_Id; Hop count: 3; Resolved: yes; Path: PolicyIdReference_Work.Policy_Id → exp_to_derive_new_policy_nb.Policy_Id → SQ_PolicyIdReference_Xt.Policy_Id → PolicyIdReference_Xt.Policy_Id [wf_4202_fnd_rltinteraction.XML:LINEAGE:PolicyIdReference_Work:Policy_Id:fa909df2]

- RLTInteractionAgreement.EProdSource_Cd — Mapping: m_4202_dt_chn_rltinteractionagreement; Folder: srctgt_EINTERACTION; Target: RLTInteractionAgreement.EProdSource_Cd; Source: PolicyIdReference_Xt.Source_Cd; Hop count: 7; Resolved: yes; Path: RLTInteractionAgreement.EProdSource_Cd → exp_assign_row_number.EprodSource_Cd → jnr_to_get_max_surrogate_key.EprodSource_Cd → SQ_RLTInteractionAgreement.EprodSource_Cd → PolicyIdReference_Work.Source_Cd → exp_to_derive_new_policy_nb.Source_Cd → SQ_PolicyIdReference_Xt.Source_Cd → PolicyIdReference_Xt.Source_Cd [wf_4202_fnd_rltinteraction.XML:LINEAGE:RLTInteractionAgreement:EProdSource_Cd:fedb9331]

- PolicyIdReference_Work.Source_Cd — Mapping: m_4202_dt_chn_rltinteractionagreement; Folder: srctgt_EINTERACTION; Target: PolicyIdReference_Work.Source_Cd; Source: PolicyIdReference_Xt.Source_Cd; Hop count: 3; Resolved: yes; Path: PolicyIdReference_Work.Source_Cd → exp_to_derive_new_policy_nb.Source_Cd → SQ_PolicyIdReference_Xt.Source_Cd → PolicyIdReference_Xt.Source_Cd [wf_4202_fnd_rltinteraction.XML:LINEAGE:PolicyIdReference_Work:Source_Cd:50a25bda]

- PolicyIdReference_Work.SourcePriority_Nb — Mapping: m_4202_dt_chn_rltinteractionagreement; Folder: srctgt_EINTERACTION; Target: PolicyIdReference_Work.SourcePriority_Nb; Source: PolicyIdReference_Xt.SourcePriority_Nb; Hop count: 3; Resolved: yes; Path: PolicyIdReference_Work.SourcePriority_Nb → exp_to_derive_new_policy_nb.SourcePriority_Nb → SQ_PolicyIdReference_Xt.SourcePriority_Nb → PolicyIdReference_Xt.SourcePriority_Nb [wf_4202_fnd_rltinteraction.XML:LINEAGE:PolicyIdReference_Work:SourcePriority_Nb:6bb7ae22]

---

## 9. What logic exists in wf_4203_calculate_interaction_facts_fbl.XML?

- id: ans_013
- strategy: llm_primary
- llm_used: True
- llm_error: None
- answer_chars: 2037
- elapsed_sec: 29.23

### Ground Truth

wf_4203_calculate_interaction_facts_fbl.XML includes logic across source, transformation, and target steps. Notable entities include exp_to_derive_surroagate_key, lkp_basecampaign, InteractionGroupStatus.

### Answer

- There is a Lookup Procedure transformation named lkp_xref_xt (mapping m_4203_fnd_interactiongroupstatus_fbl) with ports: TRANSLATIONRULETABLE_ID [LOOKUP], TARGET_TP [LOOKUP/RETURN/OUTPUT], XREF_CODE_VALUE [LOOKUP], in_TRANSLATIONRULETABLE_ID [INPUT], and in_CODEVALUE [INPUT] [wf_4203_calculate_interaction_facts_fbl.XML:TRANSFORMATION:lkp_xref_xt:543f431b].

- There is an Expression transformation exp_set_default_Tp_values that implements defaulting logic:
  - o_Status_Tp = IIF(NOT ISNULL(Status_Tp), Status_Tp, -2)
  - o_StatusReason_Tp = IIF(NOT ISNULL(StatusReason_Tp), StatusReason_Tp, -2)
  [wf_4203_calculate_interaction_facts_fbl.XML:TRANSFORMATION:exp_set_default_Tp_values:1ae966d7].

- There is an Expression transformation exp_to_derive_surroagate_key (mapping m_4203_fnd_factlessinteractionevent_fbl) with many INPUT/OUTPUT ports (examples shown): InteractionUnstructAddress_Id, Address_Id, BaseCampaign_Id, InteractionGroupStatus_Id, LeadInteraction_Id, li_Campaign_Id, big_BaseInteractionGroup_Id, src_InteractionGroup_Id, src_SequenceStart_It, src_Source_Cd, src_NUMBER_SEQ, src_Agent_Id, src_Claim_Id, src_InteractionEvent_Id, src_InteractionGroupBusinessKey_Id, etc., each listed as INPUT/OUTPUT and assigned (e.g., InteractionUnstructAddress_Id [INPUT/OUTPUT] decimal = InteractionUnstructAddress_Id) [wf_4203_calculate_interaction_facts_fbl.XML:TRANSFORMATION:exp_to_derive_surroagate_key:7fd3d866].

- The mapping reads a source EINTR_ID_XT (Teradata table FND_EINTR_WORKDB) with fields id_field_nm, source_cd, key_cd, anchor_id, insert_ts [wf_4203_calculate_interaction_facts_fbl.XML:SOURCE:EINTR_ID_XT:fe4b7e2f].

- Lineage shows FactlessInteractionEvent.InteractionGroup_Id is resolved from EINTR_ID_XT.anchor_id through a chain of transformations (including exp_to_derive_surroagate_key and several lookups/filters), indicating the InteractionGroup_Id flows from EINTR_ID_XT.anchor_id to the target [wf_4203_calculate_interaction_facts_fbl.XML:LINEAGE:FactlessInteractionEvent:InteractionGroup_Id:47d715c5].

---

## 10. Find SQL override in wf_4203_calculate_interaction_facts_fbl.XML

- id: ans_015
- strategy: llm_primary
- llm_used: True
- llm_error: None
- answer_chars: 877
- elapsed_sec: 27.06

### Ground Truth

wf_4203_calculate_interaction_facts_fbl.XML contains Source Qualifier SQL override logic, including SQ_FactlessInteractionEvent.

### Answer

The SQL override for transformation SQ_Override_SAF_FactlessInteractionEvent is:

SELECT O.FactlessInteractionEvent_Id, O.InteractionGroup_Id, O.NewExpiration_Dt, O.NewRevision_Ts, O.NewSequenceEnd_It, O.Source_Cd FROM ( SELECT FactlessInteractionEvent_Id, InteractionGroup_Id, Source_Cd, COALESCE ( MIN ( Effective_Dt) OVER (PARTITION BY InteractionGroup_Id ORDER BY Effective_Dt ASC, SequenceStart_It ASC ROWS BETWEEN 1 FOLLOWING AND 1 FOLLOWING), DATE '3500-01-01') AS NewExpiration_Dt, COALESCE ( MIN ( Transaction_Ts) OVER (PARTITION BY InteractionGroup_Id ORDER BY Transaction_Ts ASC, SequenceStart_It ASC ROWS BETWEEN 1 FOLLOWING AND 1 FOLLOWING), TIMESTAMP '3500-01-01 00:00:00.000000') AS NewRevision_Ts, COALESCE ( MIN ( SequenceStart_It) OVER (PARTITI...

[wf_4203_calculate_interaction_facts_fbl.XML:TRANSFORMATION:SQ_Override_SAF_FactlessInteractionEvent:636a6bff]

---

## 11. Find lineage records in wf_4203_calculate_interaction_facts_fbl.XML

- id: ans_016
- strategy: llm_primary
- llm_used: True
- llm_error: None
- answer_chars: 1327
- elapsed_sec: 13.38

### Ground Truth

wf_4203_calculate_interaction_facts_fbl.XML has field-level lineage through CONNECTOR paths. Key fields include src_Transaction_Ts, Transaction_Ts.

### Answer

Found one lineage record in wf_4203_calculate_interaction_facts_fbl.XML:

- FILE / NODE_CLASS / MAPPING / FOLDER / TARGET / SOURCE / HOP_COUNT / RESOLVED / PATH:
  FILE: wf_4203_calculate_interaction_facts_fbl.XML; NODE_CLASS: LINEAGE; MAPPING: m_4203_fnd_factlessinteractionevent_fbl; FOLDER: srctgt_EINTERACTION; TARGET: FactlessInteractionEvent.InteractionGroup_Id; SOURCE: EINTR_ID_XT.anchor_id; HOP_COUNT: 15; RESOLVED: yes; PATH: [TARGET ] FactlessInteractionEvent.InteractionGroup_Id -> SQ_Override_SAF_FactlessInteractionEvent.InteractionGroup_Id -> FactlessInteractionEvent1.InteractionGroup_Id -> exp_to_derive_surroagate_key.src_InteractionGroup_Id -> lkp_unstructuredaddress.src_InteractionGroup_Id -> fil_to_get_only_matched_records_from_bc.src_InteractionGroup_Id -> lkp_basecampaign.src_InteractionGroup_Id -> fil_to_get_only_matched_records_from_igs.src_InteractionGroup_Id -> lkp_IGS.src_InteractionGroup_Id -> fil_to_get_only_matched_records_from_li.src_InteractionGroup_Id -> lkp_leadinteraction.src_InteractionGroup_Id -> fil_to_get_only_matched_records.src_InteractionGroup_Id -> lkp_big.src_InteractionGroup_Id -> exp_to_hardcode_source_cd_value_with_FBL.InteractionGroup_Id (truncated in source) [wf_4203_calculate_interaction_facts_fbl.XML:LINEAGE:FactlessInteractionEvent:InteractionGroup_Id:47d715c5].

---

## 12. What logic exists in wf_4204_fnd_rltinteraction_fbl.XML?

- id: ans_017
- strategy: grounded_relevance_fallback
- llm_used: True
- llm_error: None
- answer_chars: 1382
- elapsed_sec: 61.48

### Ground Truth

wf_4204_fnd_rltinteraction_fbl.XML includes logic across source, transformation, and target steps. Notable entities include SQ_Override_DateChain_RLTInteractionAgreement, SQ_RLTInteractionAgreement, RLTInteractionAgreement.

### Answer

Based on retrieved Informatica evidence, logic in wf_4204_fnd_rltinteraction_fbl.xml appears in these nodes:
- LINEAGE: FBL_RLTInteractionAgrmt_Work.InteractionGroupKey_Cd (wf_4204_fnd_rltinteraction_fbl.XML) -> FILE: wf_4204_fnd_rltinteraction_fbl.XML NODE_CLASS: LINEAGE MAPPING: m_4202_dt_chn_rltinteractionagreement FOLDER: srctgt_EINTERACTION TARGET: FBL_RLTInteractionAgrmt_Work.InteractionGroupKey_Cd SOURCE: LBK_XREF.Inte... [wf_4204_fnd_rltinteraction_fbl.XML:LINEAGE:FBL_RLTInteractionAgrmt_Work:InteractionGroupKey_Cd:9a04786c]
- LINEAGE: FBL_RLTInteractionAgrmt_Work.InteractionGroup_Id (wf_4204_fnd_rltinteraction_fbl.XML) -> FILE: wf_4204_fnd_rltinteraction_fbl.XML NODE_CLASS: LINEAGE MAPPING: m_4202_dt_chn_rltinteractionagreement FOLDER: srctgt_EINTERACTION TARGET: FBL_RLTInteractionAgrmt_Work.InteractionGroup_Id SOURCE: EINTR_ID_XT.anch... [wf_4204_fnd_rltinteraction_fbl.XML:LINEAGE:FBL_RLTInteractionAgrmt_Work:InteractionGroup_Id:021173bd]
- LINEAGE: RLTInteractionAgreement.InteractionGroupKey_Cd (wf_4204_fnd_rltinteraction_fbl.XML) -> FILE: wf_4204_fnd_rltinteraction_fbl.XML NODE_CLASS: LINEAGE MAPPING: m_4202_dt_chn_rltinteractionagreement FOLDER: srctgt_EINTERACTION TARGET: RLTInteractionAgreement.InteractionGroupKey_Cd SOURCE: LBK_XREF.Interacti... [wf_4204_fnd_rltinteraction_fbl.XML:LINEAGE:RLTInteractionAgreement:InteractionGroupKey_Cd:f4b84fe1]

---

## 13. Find SQL override in wf_4204_fnd_rltinteraction_fbl.XML

- id: ans_019
- strategy: llm_primary
- llm_used: True
- llm_error: None
- answer_chars: 2172
- elapsed_sec: 33.33

### Ground Truth

wf_4204_fnd_rltinteraction_fbl.XML contains Source Qualifier SQL override logic, including SQ_Override_DateChain_RLTInteractionAgreement.

### Answer

The file contains these Source Qualifier transformations with SQL_OVERRIDE values:

1) TRANSFORMATION: SQ_RLTInteractionAgreement — SQL_OVERRIDE (as shown): "SELECT COALESCE(XT.anchor_id,-1) AS InteractionGroup_Id ,LBK_XREF1.InteractionGrpLogiclBusnKey_Cd AS InteractionGroupKey_Cd ,SRC.EIntrPolicyKey_Cd AS EIntrPolicyKey_Cd_Cur ,SRC1.EIntrPolicyKey_Cd AS EIntrPolicyKey_Cd_Pre ,SRC.Policy_Id AS Policy_Id_Cur ,SRC1.Policy_Id AS Policy_Id_Pre ,SRC.EIntrSource_Cd AS EIntrSource_Cd_Cur ,SRC1.EIntrSource_Cd AS EIntrSo..." [wf_4204_fnd_rltinteraction_fbl.XML:TRANSFORMATION:SQ_RLTInteractionAgreement:459cf639#0]

2) TRANSFORMATION: SQ_RLTInteractionagrmt_FBL_Work — SQL_OVERRIDE (as shown): "SELECT ROW_NUMBER() OVER (ORDER BY TMP.InteractionGroup_Id,TMP.SequenceStart_It ) NUMBER_SEQ ,InteractionGroup_Id ,InteractionGroupKey_Cd ,Policy_Id ,EIntrPolicyKey_Cd ,EIntrSource_Cd ,EProdSource_Cd ,Effective_Dt ,Expiration_Dt ,Transaction_Ts ,Revision_Ts ,SequenceStart_It ,SequenceEnd_It ,LoadEvent_Id FROM ( SELECT InteractionGroup_Id AS InteractionGroup_Id ,InteractionGroupKey_Cd AS Inter..." [wf_4204_fnd_rltinteraction_fbl.XML:TRANSFORMATION:SQ_RLTInteractionagrmt_FBL_Work:780b8dea#0]

3) TRANSFORMATION: SQ_Override_DateChain_RLTInteractionAgreement — SQL_OVERRIDE (as shown): "SELECT O.RltInteractionAgreement_Id, O.InteractionGroup_Id, O.EIntrSource_Cd, O.NewExpiration_Dt, O.NewRevision_Ts, O.NewSequenceEnd_It FROM ( SELECT RltInteractionAgreement_Id, InteractionGroup_Id, EIntrSource_Cd, COALESCE ( MIN ( Effective_Dt) OVER (PARTITION BY InteractionGroup_Id ORDER BY Effective_Dt ASC, SequenceStart_It ASC ROWS BETWEEN 1 FOLLOWING AND 1 FOLLOWING), DATE '3500-01-01') AS NewExpiration_Dt, COALESCE ( MIN ( Transaction_Ts) OVER (PARTITION BY InteractionGroup_Id ORDER BY Transaction_Ts ASC, SequenceStart_It ASC ROWS BETWEEN 1 FOLLOWING AND 1 FOLLOWING), TIMESTAMP '3500-01-01 00:00:00.000000') AS NewRevision_Ts, COALESCE ( MIN ( SequenceStart_It) OVER (PARTITION B..." [wf_4204_fnd_rltinteraction_fbl.XML:TRANSFORMATION:SQ_Override_DateChain_RLTInteractionAgreement:1c75ad5e]

If you need the full, untruncated SQL text, I cannot find it in the provided evidence.

---

## 14. Find lineage records in wf_4204_fnd_rltinteraction_fbl.XML

- id: ans_020
- strategy: llm_primary
- llm_used: True
- llm_error: None
- answer_chars: 2650
- elapsed_sec: 25.68

### Ground Truth

wf_4204_fnd_rltinteraction_fbl.XML has field-level lineage through CONNECTOR paths. Key fields include RltInteractionAgreement_Id, InteractionGroup_Id.

### Answer

Found the following lineage records in wf_4204_fnd_rltinteraction_fbl.XML:

- RLTInteractionAgreement.InteractionGroup_Id — mapping m_4202_dt_chn_rltinteractionagreement; folder srctgt_EINTERACTION; source EINTR_ID_XT.anchor_id; hop_count 9; resolved yes; path includes SQ_Override_DateChain_RLTInteractionAgreement → exp_to_derive_row_id → SQ_RLTInteractionagrmt_FBL_Work → FBL_RLTInteractionAgrmt_Work → exp_to_derive_attributes → exp_to_derive_orginating_source_cd_Flag → SQ_RLTInteractionAgreement → EINTR_ID_XT.anchor_id [wf_4204_fnd_rltinteraction_fbl.XML:LINEAGE:RLTInteractionAgreement:InteractionGroup_Id:6dd79774]

- FBL_RLTInteractionAgrmt_Work.InteractionGroup_Id — mapping m_4202_dt_chn_rltinteractionagreement; folder srctgt_EINTERACTION; source EINTR_ID_XT.anchor_id; hop_count 4; resolved yes; path includes exp_to_derive_attributes → exp_to_derive_orginating_source_cd_Flag → SQ_RLTInteractionAgreement → EINTR_ID_XT.anchor_id [wf_4204_fnd_rltinteraction_fbl.XML:LINEAGE:FBL_RLTInteractionAgrmt_Work:InteractionGroup_Id:021173bd]

- RLTInteractionAgreement.InteractionGroup_Id — mapping m_4202_dt_chn_rltinteractionagreement; folder srctgt_EINTERACTION; source EINTR_ID_XT.anchor_id; hop_count 7; resolved yes; path includes exp_to_derive_row_id → SQ_RLTInteractionagrmt_FBL_Work → FBL_RLTInteractionAgrmt_Work → exp_to_derive_attributes → exp_to_derive_orginating_source_cd_Flag → SQ_RLTInteractionAgreement → EINTR_ID_XT.anchor_id [wf_4204_fnd_rltinteraction_fbl.XML:LINEAGE:RLTInteractionAgreement:InteractionGroup_Id:5cfe129f]

- RLTInteractionAgreement.InteractionGroup_Id — mapping m_4202_dt_chn_rltinteractionagreement; folder srctgt_EINTERACTION; source EINTR_ID_XT.anchor_id; hop_count 11; resolved yes; path includes SQ_Override_DateChain_RLTInteractionAgreement → exp_to_derive_row_id → SQ_RLTInteractionagrmt_FBL_Work → FBL_RLTInteractionAgrmt_Work → exp_to_derive_attributes → exp_to_derive_orginating_source_cd_Flag → SQ_RLTInteractionAgreement → EINTR_ID_XT.anchor_id [wf_4204_fnd_rltinteraction_fbl.XML:LINEAGE:RLTInteractionAgreement:InteractionGroup_Id:256e99a1]

- RLTInteractionAgreement.InteractionGroup_Id — mapping m_4202_dt_chn_rltinteractionagreement; folder srctgt_EINTERACTION; source EINTR_ID_XT.anchor_id; hop_count 15; resolved yes; path shows repeated SQ_Override_DateChain_RLTInteractionAgreement steps leading back to SQ_RLTInteractionagrmt_FBL_Work → FBL_RLTInteractionAgrmt_Work → exp_to_derive_attributes → exp_to_derive_orginating_source_cd_Flag → SQ_RLTInteractionAgreement → EINTR_ID_XT.anchor_id [wf_4204_fnd_rltinteraction_fbl.XML:LINEAGE:RLTInteractionAgreement:InteractionGroup_Id:44b56895]

---

## 15. What logic exists in wf_4205_calculate_dm_facts.XML?

- id: ans_021
- strategy: llm_primary
- llm_used: True
- llm_error: None
- answer_chars: 1447
- elapsed_sec: 27.37

### Ground Truth

wf_4205_calculate_dm_facts.XML includes logic across source, transformation, and target steps. Notable entities include SQ_FactSaleCallActivity, JNRTRANS, Wk_BaseInteractiongroup_IVR_ARL_CALLS.

### Answer

I can describe the logic steps present in wf_4205_calculate_dm_facts.XML based on the provided lineage evidence:

- The mapping involved is m_4205_fnd_FactSaleCallActivity in folder srctgt_EINTERACTION and the source field shown is InteractionEvent.ProvidingSystemSource_Cd [9529539d].
- Source staging: SQ_InteractionEvent (source qualifier) feeds the mapping [9529539d].
- An expression transformation named Exp_RowType is applied after the source qualifier [9529539d].
- There is a filter that restricts to only CTM first instances (Filter_Restrict_Only_CTM_First_Instance) in some paths [f149a4a7].
- There is a filter that restricts to only Quote and Bind events (Restrict_Only_Quote_and_Bind) in the flow [f88086b4].
- A join by interaction party based on ECN (Jnr_Interaction_Party_basedonECN) is used in the transformation chain [f88086b4].
- A join to form a base interaction group (Jnr_BaseInteractiongroup) is performed [9529539d].
- A Restrict_BasedonDateRange transformation enforces date-range-based filtering [9529539d].
- The flow joins to historical DM XREF (jnr_dm_xref_ctm_hist) and applies a filter flt_dm_xref_ctm before populating targets [f88086b4].
- Targets include DM_XREF_CTM, dm_xref_ctm_zoom and DM_XREF_CTM_HIST populated from the above flow from InteractionEvent.ProvidingSystemSource_Cd [48c440a2][f149a4a7][e597a521].

Each claim above is supported by the cited lineage entries from wf_4205_calculate_dm_facts.XML.

---

## 16. Where is SQ_FactSaleCallActivity used?

- id: ans_022
- strategy: llm_relevancy_rewrite
- llm_used: True
- llm_error: None
- answer_chars: 1179
- elapsed_sec: 32.36

### Ground Truth

SQ_FactSaleCallActivity is used in wf_4205_calculate_dm_facts.XML as part of the mapping transformation flow.

### Answer

- I found no reference to "SQ_FactSaleCallActivity" in the provided evidence [wf_2216_source_saf_interaction_synm_text.XML:TRANSFORMATION:exp_straight_move_default_hardcode_value:f1d58761#3] [wf_2201_source_saf_interactions_errors_campaigns.XML:TRANSFORMATION:SQ_CAMPAIGN_PARENT_CAMPAIGN:56e97ad7] [wf_4201_calculate_interaction_facts.XML:TRANSFORMATION:SQ_SQL_Override_FactLeadActivity:4c59eba0#9] [wf_2201_source_saf_interactions_errors_campaigns.XML:TRANSFORMATION:exp_SAF_Keys_Defaults:7bdd8a3a].  
- The provided transformations inspected were exp_straight_move_default_hardcode_value, SQ_CAMPAIGN_PARENT_CAMPAIGN, SQ_SQL_Override_FactLeadActivity, and exp_SAF_Keys_Defaults; none of these contain or use SQ_FactSaleCallActivity in the shown excerpts [wf_2216_source_saf_interaction_synm_text.XML:TRANSFORMATION:exp_straight_move_default_hardcode_value:f1d58761#3] [wf_2201_source_saf_interactions_errors_campaigns.XML:TRANSFORMATION:SQ_CAMPAIGN_PARENT_CAMPAIGN:56e97ad7] [wf_4201_calculate_interaction_facts.XML:TRANSFORMATION:SQ_SQL_Override_FactLeadActivity:4c59eba0#9] [wf_2201_source_saf_interactions_errors_campaigns.XML:TRANSFORMATION:exp_SAF_Keys_Defaults:7bdd8a3a].

---

## 17. Find SQL override in wf_4205_calculate_dm_facts.XML

- id: ans_023
- strategy: llm_relevancy_rewrite
- llm_used: True
- llm_error: None
- answer_chars: 902
- elapsed_sec: 21.45

### Ground Truth

wf_4205_calculate_dm_facts.XML contains Source Qualifier SQL override logic, including SQ_SQL_Override_DM_FactSaleCallActivity.

### Answer

- The SQL override is in TRANSFORMATION "SQ_SQL_Override_bind_dm_xref_final_ph" (a Source Qualifier) in wf_4205_calculate_dm_facts.XML [wf_4205_calculate_dm_facts.XML:TRANSFORMATION:SQ_SQL_Override_bind_dm_xref_final_ph:437789fa#0].  
- That Source Qualifier is used by mapping m_4205_dm_FactSaleCallActivity_load and exposes many ports (e.g., InteractionGroup_Id, Sequence_It, Source_Cd, Transaction_Dt, InteractingPartyPhone_Nb) [wf_4205_calculate_dm_facts.XML:TRANSFORMATION:SQ_SQL_Override_bind_dm_xref_final_ph:437789fa#0].  
- The workflow also contains SQL-related custom transformations: "jav_print_sql_number_of_rows_affected" (has SQL port) [wf_4205_calculate_dm_facts.XML:TRANSFORMATION:jav_print_sql_number_of_rows_affected:a6ce49c6] and "sql_recursive_sql_with_conditions" (SQL input/output ports) [wf_4205_calculate_dm_facts.XML:TRANSFORMATION:sql_recursive_sql_with_conditions:48101968].

---

## 18. Find lineage records in wf_4205_calculate_dm_facts.XML

- id: ans_024
- strategy: grounded_relevance_fallback
- llm_used: True
- llm_error: None
- answer_chars: 1295
- elapsed_sec: 57.99

### Ground Truth

wf_4205_calculate_dm_facts.XML has field-level lineage through CONNECTOR paths. Key fields include TransferredCall_Ct, FirstSalesCall_Ct.

### Answer

Based on retrieved Informatica evidence, lineage records supporting this request are:
- LINEAGE: FactSaleCallActivity.AnalyticParty_Id (wf_4205_calculate_dm_facts.XML) -> FILE: wf_4205_calculate_dm_facts.XML NODE_CLASS: LINEAGE MAPPING: m_4205_fnd_FactSaleCallActivity FOLDER: srctgt_EINTERACTION TARGET: FactSaleCallActivity.AnalyticParty_Id SOURCE: BaseParty.AnalyticParty_Id HOP_COUNT:... [wf_4205_calculate_dm_facts.XML:LINEAGE:FactSaleCallActivity:AnalyticParty_Id:b3aa621b]
- LINEAGE: FactSaleCallActivity.AnalyticHousehold_Id (wf_4205_calculate_dm_facts.XML) -> FILE: wf_4205_calculate_dm_facts.XML NODE_CLASS: LINEAGE MAPPING: m_4205_fnd_FactSaleCallActivity FOLDER: srctgt_EINTERACTION TARGET: FactSaleCallActivity.AnalyticHousehold_Id SOURCE: BaseParty.AnalyticHousehold_Id HO... [wf_4205_calculate_dm_facts.XML:LINEAGE:FactSaleCallActivity:AnalyticHousehold_Id:8edeb41d]
- LINEAGE: dm_xref_priorityhhforphone.AnalyticHousehold_Id (wf_4205_calculate_dm_facts.XML) -> FILE: wf_4205_calculate_dm_facts.XML NODE_CLASS: LINEAGE MAPPING: m_4205_fnd_FactSaleCallActivity FOLDER: srctgt_EINTERACTION TARGET: dm_xref_priorityhhforphone.AnalyticHousehold_Id SOURCE: BaseParty.AnalyticHousehold... [wf_4205_calculate_dm_facts.XML:LINEAGE:dm_xref_priorityhhforphone:AnalyticHousehold_Id:5456eb22]

---

## 19. What logic exists in wf_4206_calculate_facts_fcr.XML?

- id: ans_025
- strategy: llm_primary
- llm_used: True
- llm_error: None
- answer_chars: 1574
- elapsed_sec: 30.11

### Ground Truth

wf_4206_calculate_facts_fcr.XML includes logic across source, transformation, and target steps. Notable entities include SQ_FactFirstCallResolution, exp_DDL_default, FactCallActivityConnection.

### Answer

The workflow contains a mapping m_4206_wk_FactFirstCallResolution_wk_UPD (folder srctgt_EINTERACTION) that populates the target table FactFCR_Eligible from the source FactCallActivityConnection via the SQ_Sqloverride_Exclude_MultiCTM transformation (path: FactFCR_Eligible → SQ_Sqloverride_Exclude_MultiCTM → FactCallActivityConnection) [wf_4206_calculate_facts_fcr.XML:LINEAGE:FactFCR_Eligible:BeginAnalyticParty_Id:a4d91458].

Specific column-level logic shown in the file maps these source→target columns through that SQ transformation:
- BeginAnalyticParty_Id: FactCallActivityConnection.BeginAnalyticParty_Id → FactFCR_Eligible.BeginAnalyticParty_Id [wf_4206_calculate_facts_fcr.XML:LINEAGE:FactFCR_Eligible:BeginAnalyticParty_Id:a4d91458]
- BeginCallRouted_Ts: FactCallActivityConnection.BeginCallRouted_Ts → FactFCR_Eligible.BeginCallRouted_Ts [wf_4206_calculate_facts_fcr.XML:LINEAGE:FactFCR_Eligible:BeginCallRouted_Ts:18d57e98]
- EndAnalyticParty_Id: FactCallActivityConnection.EndAnalyticParty_Id → FactFCR_Eligible.EndAnalyticParty_Id [wf_4206_calculate_facts_fcr.XML:LINEAGE:FactFCR_Eligible:EndAnalyticParty_Id:c5ba7513]
- EndAdditionalTopicDescription_Tt: FactCallActivityConnection.EndAdditionalTopicDescr_Tt → FactFCR_Eligible.EndAdditionalTopicDescription_Tt [wf_4206_calculate_facts_fcr.XML:LINEAGE:FactFCR_Eligible:EndAdditionalTopicDescription_Tt:3b899e75]
- BeginCallPurpose_Cd: FactCallActivityConnection.BeginCallPurpose_Cd → FactFCR_Eligible.BeginCallPurpose_Cd [wf_4206_calculate_facts_fcr.XML:LINEAGE:FactFCR_Eligible:BeginCallPurpose_Cd:9fa670cc]

---

## 20. Where is SQ_FactFirstCallResolution used?

- id: ans_026
- strategy: llm_relevancy_rewrite
- llm_used: True
- llm_error: None
- answer_chars: 840
- elapsed_sec: 24.63

### Ground Truth

SQ_FactFirstCallResolution is used in wf_4206_calculate_facts_fcr.XML as part of the mapping transformation flow.

### Answer

- The provided wf_4206 file contains a TRANSFORMATION named SQ_FactFCR_Eligible (in wf_4206_calculate_facts_fcr.XML) — not SQ_FactFirstCallResolution [wf_4206_calculate_facts_fcr.XML:TRANSFORMATION:SQ_FactFCR_Eligible:c76e4bbc#3].  
- The other provided snippet shows a TRANSFORMATION derive_attributes_values in wf_2208 (wf_2208_source_saf_interaction_fbl.XML) and does not reference SQ_FactFirstCallResolution [wf_2208_source_saf_interaction_fbl.XML:TRANSFORMATION:derive_attributes_values:d29a8f15#4].  
- Based on these provided chunks, SQ_FactFirstCallResolution is not present in the evidence shown (only SQ_FactFCR_Eligible and derive_attributes_values appear) [wf_4206_calculate_facts_fcr.XML:TRANSFORMATION:SQ_FactFCR_Eligible:c76e4bbc#3] [wf_2208_source_saf_interaction_fbl.XML:TRANSFORMATION:derive_attributes_values:d29a8f15#4].

---

## 21. Find SQL override in wf_4206_calculate_facts_fcr.XML

- id: ans_027
- strategy: llm_relevancy_rewrite
- llm_used: True
- llm_error: None
- answer_chars: 1055
- elapsed_sec: 37.99

### Ground Truth

wf_4206_calculate_facts_fcr.XML contains Source Qualifier SQL override logic, including SQ_FactFirstCallResolution.

### Answer

- The SQL override used is SQ_Sqloverride_Exclude_MultiCTM in wf_4206_calculate_facts_fcr.XML (transformation name shown in the mapping) [wf_4206_calculate_facts_fcr.XML:LINEAGE:FactFCR_Eligible:EndTransactionEffective_Dt:e4dc8192].  
- It is applied to FactFCR_Eligible target fields: EndTransactionEffective_Dt [wf_4206_calculate_facts_fcr.XML:LINEAGE:FactFCR_Eligible:EndTransactionEffective_Dt:e4dc8192], EndAnalyticParty_Id [wf_4206_calculate_facts_fcr.XML:LINEAGE:FactFCR_Eligible:EndAnalyticParty_Id:c5ba7513], BeginTransactionEffective_Dt [wf_4206_calculate_facts_fcr.XML:LINEAGE:FactFCR_Eligible:BeginTransactionEffective_Dt:02385abd], and BeginSourceTransaction_Ts [wf_4206_calculate_facts_fcr.XML:LINEAGE:FactFCR_Eligible:BeginSourceTransaction_Ts:e0e3d0ae].  
- Each mapping shows the source as FactCallActivityConnection.<field> to target FactFCR_Eligible.<field> with HOP_COUNT: 2 and RESOLVED: yes (i.e., the override is active in that mapping) [wf_4206_calculate_facts_fcr.XML:LINEAGE:FactFCR_Eligible:EndTransactionEffective_Dt:e4dc8192].

---

## 22. Find lineage records in wf_4206_calculate_facts_fcr.XML

- id: ans_028
- strategy: llm_primary
- llm_used: True
- llm_error: None
- answer_chars: 2105
- elapsed_sec: 28.8

### Ground Truth

wf_4206_calculate_facts_fcr.XML has field-level lineage through CONNECTOR paths. Key fields include FactFirstCallResolution_Id, v_default_decimal.

### Answer

The file wf_4206_calculate_facts_fcr.XML contains the following lineage records:

- FactFCR_Eligible.BeginAnalyticHousehold_Id — MAPPING: m_4206_wk_FactFirstCallResolution_wk_UPD; FOLDER: srctgt_EINTERACTION; SOURCE: FactCallActivityConnection.BeginAnalyticHousehold_Id; HOP_COUNT: 2; RESOLVED: yes; PATH shows SQ_Sqloverride_Exclude_MultiCTM.BeginAnalyticHousehold_Id → FactFCR_Eligible.BeginAnalyticHousehold_Id [wf_4206_calculate_facts_fcr.XML:LINEAGE:FactFCR_Eligible:BeginAnalyticHousehold_Id:79bef3d3].

- FactFCR_Eligible.EndAnalyticHousehold_Id — MAPPING: m_4206_wk_FactFirstCallResolution_wk_UPD; FOLDER: srctgt_EINTERACTION; SOURCE: FactCallActivityConnection.EndAnalyticHousehold_Id; HOP_COUNT: 2; RESOLVED: yes; PATH shows SQ_Sqloverride_Exclude_MultiCTM.EndAnalyticHousehold_Id → FactFCR_Eligible.EndAnalyticHousehold_Id [wf_4206_calculate_facts_fcr.XML:LINEAGE:FactFCR_Eligible:EndAnalyticHousehold_Id:f9280d4f].

- FactFCR_Eligible.BeginAnalyticParty_Id — MAPPING: m_4206_wk_FactFirstCallResolution_wk_UPD; FOLDER: srctgt_EINTERACTION; SOURCE: FactCallActivityConnection.BeginAnalyticParty_Id; HOP_COUNT: 2; RESOLVED: yes; PATH shows SQ_Sqloverride_Exclude_MultiCTM.BeginAnalyticParty_Id → FactFCR_Eligible.BeginAnalyticParty_Id [wf_4206_calculate_facts_fcr.XML:LINEAGE:FactFCR_Eligible:BeginAnalyticParty_Id:a4d91458].

- FactFCR_Eligible.EndAnalyticParty_Id — MAPPING: m_4206_wk_FactFirstCallResolution_wk_UPD; FOLDER: srctgt_EINTERACTION; SOURCE: FactCallActivityConnection.EndAnalyticParty_Id; HOP_COUNT: 2; RESOLVED: yes; PATH shows SQ_Sqloverride_Exclude_MultiCTM.EndAnalyticParty_Id → FactFCR_Eligible.EndAnalyticParty_Id [wf_4206_calculate_facts_fcr.XML:LINEAGE:FactFCR_Eligible:EndAnalyticParty_Id:c5ba7513].

- FactFCR_Eligible.BeginSource_Cd — MAPPING: m_4206_wk_FactFirstCallResolution_wk_UPD; FOLDER: srctgt_EINTERACTION; SOURCE: FactCallActivityConnection.BeginSource_Cd; HOP_COUNT: 2; RESOLVED: yes; PATH shows SQ_Sqloverride_Exclude_MultiCTM.BeginSource_Cd → FactFCR_Eligible.BeginSource_Cd [wf_4206_calculate_facts_fcr.XML:LINEAGE:FactFCR_Eligible:BeginSource_Cd:4a66a4cf].

---
