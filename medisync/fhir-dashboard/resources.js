// DrChrono Native API Resource Definitions — James R. Mitchell Test Patient
// All endpoints use https://app.drchrono.com/api/* format
window.FHIR_RESOURCES = [
  {
    id:"doctors",name:"Doctors (Lookup)",endpoint:"/doctors",order:1,icon:"🩺",method:"GET",
    produces:"doctor",depends:[],
    payload:()=>({}),
    description:"GET first to obtain your doctor_id — required by all other resources."
  },
  {
    id:"offices",name:"Offices (Lookup)",endpoint:"/offices",order:2,icon:"🏢",method:"GET",
    produces:"office",depends:[],
    payload:()=>({}),
    description:"GET to obtain office_id and exam_room index — required for appointments."
  },
  {
    id:"patient",name:"Patient Creation",endpoint:"/patients",order:3,icon:"👤",method:"POST",
    produces:"patient",depends:["doctor"],
    payload:(r)=>({
      doctor: r.doctor||0,
      first_name:"James",
      last_name:"Mitchell",
      middle_name:"R",
      date_of_birth:"1985-04-12",
      gender:"Male",
      social_security_number:"",
      address:"742 N Michigan Ave, Apt 12B",
      city:"Chicago",
      state:"IL",
      zip_code:"60611",
      cell_phone:"312-555-0142",
      email:"james.mitchell@email.com",
      emergency_contact_name:"Sarah Mitchell",
      emergency_contact_phone:"312-555-0198",
      emergency_contact_relation:"Spouse",
      employer:"Midwest Financial Group",
      ethnicity:"blank",
      race:"white",
      preferred_language:"eng"
    })
  },
  {
    id:"appointment",name:"Appointments",endpoint:"/appointments",order:4,icon:"📅",method:"POST",
    produces:"appointment",depends:["doctor","patient","office"],
    payload:(r)=>({
      doctor: r.doctor||0,
      patient: r.patient||0,
      office: r.office||0,
      exam_room: 0,
      scheduled_time:"2025-06-01T09:00:00",
      duration: 30,
      status:"Confirmed",
      reason:"Follow-up: Hypertension & Hyperlipidemia management",
      notes:"Routine follow-up. Review BP logs and lipid panel.",
      profile: null,
      is_walk_in: false
    })
  },
  {
    id:"condition",name:"Conditions",endpoint:"/problems",order:5,icon:"🫀",method:"POST",
    produces:"condition",depends:["doctor","patient"],
    payload:(r)=>({
      doctor: r.doctor||0,
      patient: r.patient||0,
      date_diagnosis:"2020-03-15",
      date_onset:"2020-03-15",
      description:"Essential (primary) hypertension — Stage 1. Patient on Lisinopril 20mg daily.",
      icd_code:"I10",
      name:"Essential Hypertension",
      status:"active",
      notes:"Second condition: Hyperlipidemia (E78.5) — submit separately with same payload structure."
    })
  },
  {
    id:"allergy",name:"Allergies",endpoint:"/allergies",order:6,icon:"⚠️",method:"POST",
    produces:"allergy",depends:["doctor","patient"],
    payload:(r)=>({
      doctor: r.doctor||0,
      patient: r.patient||0,
      reaction:"Penicillin",
      notes:"Urticarial rash within 2 hours of administration. Documented since 2005.",
      status:"active",
      severity:"moderate",
      onset_date:"2005-08-01",
      reaction_type:"allergy"
    })
  },
  {
    id:"medication",name:"Medications",endpoint:"/medications",order:7,icon:"💊",method:"POST",
    produces:"medication",depends:["doctor","patient","appointment"],
    payload:(r)=>({
      doctor: r.doctor||0,
      patient: r.patient||0,
      appointment: r.appointment||0,
      name:"Lisinopril 20 MG Oral Tablet",
      rxnorm:"314076",
      dosage_quantity:"20",
      dosage_unit:"mg",
      frequency:"Once daily",
      route:"Oral",
      status:"active",
      dispense_quantity: 30,
      number_refills: 3,
      order_status:"Submitted",
      signature_note:"Take 1 tablet by mouth once daily in the morning for blood pressure.",
      pharmacy_note:"Second med: Atorvastatin 20mg PO QHS (RxNorm: 259255) — submit separately.",
      prn: false,
      daw: false
    })
  },
  {
    id:"immunization",name:"Immunizations",endpoint:"/patient_vaccine_records",order:8,icon:"💉",method:"POST",
    produces:"immunization",depends:["patient","doctor"],
    payload:(r)=>({
      patient: r.patient||0,
      doctor: r.doctor||0,
      cvx_code:"197",
      name:"Influenza, high-dose, quadrivalent (2024-2025)",
      administration_start:"2024-10-15",
      administered_at:"Office",
      route:"IM",
      site:"Left Deltoid",
      dose_quantity:"0.7",
      dose_unit:"mL",
      lot_number:"FL2024-A1234",
      expiry_date:"2025-06-30",
      status:"completed",
      notes:"Annual influenza vaccination. COVID-19 bivalent booster (CVX 309) also due — submit separately."
    })
  },
  {
    id:"observation",name:"Observations (Vitals)",endpoint:"/clinical_note_field_values",order:9,icon:"📊",method:"POST",
    produces:"observation",depends:["appointment"],
    payload:(r)=>({
      appointment: r.appointment||0,
      clinical_note_field:{},
      value:"BP: 138/88 mmHg | HR: 74 bpm | Weight: 192 lbs | BMI: 26.8 | Temp: 98.4°F | SpO2: 98% | RR: 16",
      notes:"Vitals recorded at encounter 2025-06-01. Also order TSH (1.8 mIU/L via lab). Use PATCH /api/appointments/{id} to set vitals fields directly."
    }),
    description:"DrChrono vitals are set via PATCH /api/appointments/{id} or clinical note fields."
  },
  {
    id:"observation_note",name:"Observation Notes",endpoint:"/clinical_note_field_values",order:10,icon:"📝",method:"POST",
    produces:"observation_note",depends:["appointment"],
    payload:(r)=>({
      appointment: r.appointment||0,
      clinical_note_field:{},
      value:"40-year-old male presents for routine follow-up. Reports good medication compliance with Lisinopril 20mg daily. Occasional morning headaches, no chest pain, no dyspnea. Diet modifications ongoing — reduced sodium intake. Exercises 3x/week (walking 30 min). Home BP readings range 130-140/82-90."
    }),
    description:"Free-text observation notes via clinical_note_field_values."
  },
  {
    id:"coverage",name:"Coverages",endpoint:"/patient_insurances",order:11,icon:"🛡️",method:"POST",
    produces:"coverage",depends:["patient"],
    payload:(r)=>({
      patient: r.patient||0,
      payer_name:"Blue Cross Blue Shield of Illinois",
      plan_name:"BCBS PPO Gold",
      member_id:"XKL845923701",
      group_number:"GRP-MW-44201",
      group_name:"Midwest Financial Group",
      is_subscriber_the_patient: true,
      subscriber_first_name:"James",
      subscriber_last_name:"Mitchell",
      subscriber_date_of_birth:"1985-04-12",
      insurance_type:"medical",
      start_date:"2025-01-01",
      end_date:"2025-12-31",
      copay:"25.00",
      deductible:"1500.00",
      notes:"PPO Gold plan — in-network. Employer-sponsored."
    })
  },
  {
    id:"service_request",name:"Service Requests",endpoint:"/tasks",order:12,icon:"📋",method:"POST",
    produces:"task",depends:["doctor","patient"],
    payload:(r)=>({
      title:"Order: Fasting Lipid Panel — James Mitchell",
      status:"New",
      category: 1,
      due_date:"2025-06-15",
      notes:"Fasting lipid panel for hyperlipidemia (E78.5) monitoring. Patient on Atorvastatin 20mg. Last lipids 6 months ago. Use GET /api/task_categories first for valid category IDs.",
      associated_patient: r.patient||null,
      assignee_user: r.doctor||null
    }),
    description:"Use GET /api/task_categories first to get valid category IDs."
  },
  {
    id:"diagnostic_report",name:"Diagnostic Reports",endpoint:"/lab_orders",order:13,icon:"🔬",method:"POST",
    produces:"lab_order",depends:["doctor","patient"],
    payload:(r)=>({
      doctor: r.doctor||0,
      patient: r.patient||0,
      sublab: 0,
      icd10_codes:["E78.5","I10"],
      notes:"Fasting Comprehensive Lipid Panel. Monitor cholesterol levels — patient on Atorvastatin 20mg for hyperlipidemia. Also check TSH baseline. Use GET /api/sublabs first for valid sublab IDs.",
      priority:"Normal",
      status:"O"
    }),
    description:"Use GET /api/sublabs first to get valid sublab IDs."
  },
  {
    id:"document",name:"Documents",endpoint:"/documents",order:14,icon:"📄",method:"POST",
    produces:"document",depends:["doctor","patient"],
    payload:(r)=>({
      doctor: r.doctor||0,
      patient: r.patient||0,
      description:"Office Visit Summary — Hypertension and Hyperlipidemia Follow-up — 2025-06-01",
      date:"2025-06-01",
      metatags:"visit summary, hypertension, hyperlipidemia, follow-up",
      document:"(Base64-encoded file content — use multipart/form-data for actual upload)",
      notes:"Live DrChrono requires multipart/form-data with file upload. This payload is for reference."
    }),
    description:"Live upload requires multipart/form-data. This shows the expected fields."
  },
  {
    id:"clinical_note",name:"Clinical Notes",endpoint:"/clinical_note_field_values",order:15,icon:"🗒️",method:"POST",
    produces:"clinical_note",depends:["appointment"],
    payload:(r)=>({
      appointment: r.appointment||0,
      clinical_note_field:{},
      value:"PROGRESS NOTE\nDate: 2025-06-01 | Provider: Dr. Ananya Patel, MD\n\nSUBJECTIVE: Patient reports compliance with antihypertensive and statin therapy. Occasional AM headaches. No CP/SOB.\n\nOBJECTIVE: BP 138/88, HR 74, Wt 192 lbs, BMI 26.8. CV: RRR, no murmurs. Lungs: CTA bilat.\n\nASSESSMENT:\n1. HTN (I10) - Suboptimal control. Continue Lisinopril 20mg.\n2. Hyperlipidemia (E78.5) - Lipid panel ordered. Continue Atorvastatin 20mg QHS.\n\nPLAN: Recheck BP in 6 weeks. If >135/85, uptitrate Lisinopril to 40mg."
    }),
    description:"Clinical notes are auto-created with appointments. Fill via field_values."
  },
  {
    id:"procedure",name:"Procedures",endpoint:"/procedures",order:16,icon:"🔧",method:"POST",
    produces:"procedure",depends:["doctor","patient","appointment"],
    payload:(r)=>({
      doctor: r.doctor||0,
      patient: r.patient||0,
      appointment: r.appointment||0,
      code:"80061",
      procedure_type:"CPT",
      description:"Lipid panel — venipuncture from right antecubital fossa",
      adjustment:"0.00",
      allowed:"0.00",
      balance_ins:"0.00",
      ins_total:"0.00",
      ins1_paid:"0.00",
      total:"0.00",
      icd10_codes:["E78.5"]
    })
  },
  {
    id:"care_plan",name:"Care Plan",endpoint:"/care_plans",order:17,icon:"📐",method:"POST",
    produces:"care_plan",depends:["doctor","patient"],
    payload:(r)=>({
      doctor: r.doctor||0,
      patient: r.patient||0,
      plan_name:"Cardiovascular Risk Reduction — HTN + HLD Management",
      description:"Comprehensive plan for James Mitchell:\n1. Lisinopril 20mg PO daily — monitor BP bi-weekly at home\n2. Atorvastatin 20mg PO QHS — recheck lipids in 3 months\n3. DASH diet: sodium <2300mg/day, increase fruits/vegetables\n4. Exercise: 150 min/week moderate aerobic (walking, cycling)\n5. Weight goal: reduce from 192 to 180 lbs over 6 months\n6. Follow-up: 6 weeks for BP recheck, 3 months for lipids",
      start_date:"2025-06-01",
      end_date:"2026-06-01",
      status:"active"
    })
  },
  {
    id:"care_team",name:"Care Team",endpoint:"/patient_communications",order:18,icon:"👥",method:"POST",
    produces:"care_team",depends:["doctor","patient"],
    payload:(r)=>({
      doctor: r.doctor||0,
      patient: r.patient||0,
      type:"Phone Call",
      description:"Care team coordination — Mitchell Cardiovascular Team:\n• PCP: Dr. Ananya Patel (Internal Medicine)\n• RN: Sarah Chen (Care coordination)\n• RD: Michael Torres (Dietary counseling — DASH diet)\n• PharmD: Lisa Park (Medication therapy management)\n\nDiscussed: BP trends, medication compliance, upcoming lipid panel, diet modifications. Patient engaged and motivated.",
      datetime:"2025-06-01T10:00:00"
    })
  }
];
