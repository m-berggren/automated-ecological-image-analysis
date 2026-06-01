"""
Unit tests for evaluate.ipynb metric logic.
Tests every computation function with synthetic inputs of known expected output.
Run: python test_evaluate_logic.py
"""
import sys, math
from collections import defaultdict

PASS = 0; FAIL = 0

def check(name, actual, expected, tol=1e-6):
    global PASS, FAIL
    if isinstance(expected, float):
        ok = abs(actual - expected) <= tol
    elif isinstance(expected, dict):
        ok = all(abs(actual.get(k,0) - v) <= tol for k,v in expected.items())
    else:
        ok = (actual == expected)
    sym = "✓" if ok else "✗"
    if not ok:
        print(f"  {sym} FAIL  {name}")
        print(f"       expected: {expected}")
        print(f"       got:      {actual}")
        FAIL += 1
    else:
        print(f"  {sym} PASS  {name}")
        PASS += 1

# ─────────────────────────────────────────────────────────────────────────────
# Helpers copied verbatim from evaluate.ipynb
# ─────────────────────────────────────────────────────────────────────────────

def bbox_overlap_ratio(p, g):
    ix1=max(p['x1'],g['x1']); iy1=max(p['y1'],g['y1'])
    ix2=min(p['x2'],g['x2']); iy2=min(p['y2'],g['y2'])
    iw=max(0,ix2-ix1); ih=max(0,iy2-iy1)
    gt_area=max(1,(g['x2']-g['x1'])*(g['y2']-g['y1']))
    return iw*ih/gt_area

def center_match(pred_boxes, gt_boxes, overlap_thresh=0.20):
    def inside(px,py,x1,y1,x2,y2): return x1<=px<=x2 and y1<=py<=y2
    mp=set(); mg=set(); pairs=[]
    for gi,g in enumerate(gt_boxes):
        gcx=(g['x1']+g['x2'])/2; gcy=(g['y1']+g['y2'])/2
        for pi,p in enumerate(pred_boxes):
            if pi in mp: continue
            pcx=(p['x1']+p['x2'])/2; pcy=(p['y1']+p['y2'])/2
            if (inside(gcx,gcy,p['x1'],p['y1'],p['x2'],p['y2']) or
                inside(pcx,pcy,g['x1'],g['y1'],g['x2'],g['y2']) or
                bbox_overlap_ratio(p,g)>=overlap_thresh):
                pairs.append((pi,gi)); mp.add(pi); mg.add(gi); break
    return pairs,[i for i in range(len(pred_boxes)) if i not in mp],\
                 [i for i in range(len(gt_boxes)) if i not in mg]

def evaluate_one_pipeline(preds_by_img, gt, classes, label):
    rows_out=[]; n_bg_rejected=0
    det_tp=det_fp=det_fn=0
    cls_correct=0; cls_wrong=0
    tp_c=defaultdict(int); fp_c=defaultdict(int); fn_c=defaultdict(int)
    fn_detected_as_bg=0; fn_not_detected=0
    for img_p, gt_boxes in gt.items():
        all_preds = preds_by_img.get(img_p, [])
        insect    = [p for p in all_preds if not p.get('is_bg')]
        rejected  = [p for p in all_preds if p.get('is_bg')]
        n_bg_rejected += len(rejected)
        pairs, unp, ung = center_match(insect, gt_boxes)
        for pi,gi in pairs:
            det_tp+=1
            pc=insect[pi]['cls']; gc=gt_boxes[gi]['cls']
            correct=(pc==gc)
            if correct: cls_correct+=1; tp_c[gc]+=1
            else: cls_wrong+=1; fp_c[pc]+=1; fn_c[gc]+=1
            rows_out.append({'pipeline':label,'img':img_p,'match':'tp',
                             'pred_cls':pc,'gt_cls':gc,'conf':insect[pi]['conf'],'correct_cls':correct})
        for pi in unp:
            det_fp+=1; fp_c[insect[pi]['cls']]+=1
            rows_out.append({'pipeline':label,'img':img_p,'match':'fp',
                             'pred_cls':insect[pi]['cls'],'gt_cls':'','conf':insect[pi]['conf'],'correct_cls':False})
        for gi in ung:
            det_fn+=1; fn_c[gt_boxes[gi]['cls']]+=1
            g = gt_boxes[gi]
            covered_by_bg = any(
                bbox_overlap_ratio(r,g)>=0.20 or bbox_overlap_ratio(g,r)>=0.20
                for r in rejected)
            if covered_by_bg: fn_detected_as_bg+=1; match_type='fn_detected_as_bg'
            else: fn_not_detected+=1; match_type='fn_not_detected'
            rows_out.append({'pipeline':label,'img':img_p,'match':match_type,
                             'pred_cls':'bg','gt_cls':gt_boxes[gi]['cls'],'conf':0.0,'correct_cls':False})
    det_prec=det_tp/max(1,det_tp+det_fp)
    det_rec =det_tp/max(1,det_tp+det_fn)
    det_f1  =2*det_prec*det_rec/max(1e-8,det_prec+det_rec)
    cls_acc =cls_correct/max(1,det_tp)
    return {'det_precision':det_prec,'det_recall':det_rec,'det_f1':det_f1,
            'det_tp':det_tp,'det_fp':det_fp,'det_fn':det_fn,
            'fn_detected_as_bg':fn_detected_as_bg,'fn_not_detected':fn_not_detected,
            'cls_accuracy':cls_acc,'cls_correct':cls_correct,'cls_wrong':cls_wrong,
            'n_bg_rejected':n_bg_rejected,
            'tp_c':dict(tp_c),'fp_c':dict(fp_c),'fn_c':dict(fn_c),'rows':rows_out}

def perplot_metrics(preds_by_img, gt_by_img, section_classes):
    """Cell 25 per-plot logic (after both fixes)."""
    cls_tp      = defaultdict(int)
    cls_fp      = defaultdict(int)
    cls_fn      = defaultdict(int)
    cls_correct = defaultdict(int)
    cls_wrong   = defaultdict(int)
    cls_errors  = defaultdict(lambda: defaultdict(int))
    for img_p, gt_boxes in gt_by_img.items():
        insect = [p for p in preds_by_img.get(img_p,[]) if not p.get('is_bg')]
        pairs, unp, ung = center_match(insect, gt_boxes)
        for pi,gi in pairs:
            pc=insect[pi]['cls']; gc=gt_boxes[gi]['cls']
            if pc==gc: cls_tp[gc]+=1; cls_correct[gc]+=1
            else: cls_wrong[gc]+=1; cls_errors[gc][pc]+=1; cls_fp[pc]+=1; cls_fn[gc]+=1
        for pi in unp: cls_fp[insect[pi]['cls']]+=1
        for gi in ung: cls_fn[gt_boxes[gi]['cls']]+=1
    results = {}
    for c in section_classes:
        tp=cls_tp[c]; fp=cls_fp[c]; fn=cls_fn[c]
        p=tp/max(1,tp+fp); r=tp/max(1,tp+fn)
        results[c] = {'tp':tp,'fp':fp,'fn':fn,'precision':p,'recall':r,
                      'correct':cls_correct[c],'wrong':cls_wrong[c],
                      'errors':dict(cls_errors[c])}
    return results

def combined_recall(crop_preds, yolo_preds, gt):
    """Cell 27 combined pipeline recall logic."""
    crop_only=0; yolo_only=0; both=0; neither=0
    for img_p, gt_boxes in gt.items():
        crop_ins = [p for p in crop_preds.get(img_p,[]) if not p.get('is_bg')]
        yolo_ins = yolo_preds.get(img_p, [])
        crop_pairs,_,_ = center_match(crop_ins, gt_boxes)
        yolo_pairs,_,_ = center_match(yolo_ins, gt_boxes)
        crop_matched = {gi for _,gi in crop_pairs}
        yolo_matched = {gi for _,gi in yolo_pairs}
        for gi in range(len(gt_boxes)):
            ic = gi in crop_matched; iy = gi in yolo_matched
            if ic and iy: both+=1
            elif ic: crop_only+=1
            elif iy: yolo_only+=1
            else: neither+=1
    total = crop_only+yolo_only+both+neither
    return {
        'crop_only':crop_only,'yolo_only':yolo_only,'both':both,'neither':neither,
        'total':total,
        'crop_recall':(crop_only+both)/max(1,total),
        'yolo_recall':(yolo_only+both)/max(1,total),
        'combined_recall':(crop_only+yolo_only+both)/max(1,total),
    }

def iou(p, g):
    ix1=max(p['x1'],g['x1']); iy1=max(p['y1'],g['y1'])
    ix2=min(p['x2'],g['x2']); iy2=min(p['y2'],g['y2'])
    inter=max(0,ix2-ix1)*max(0,iy2-iy1)
    union=((p['x2']-p['x1'])*(p['y2']-p['y1'])+(g['x2']-g['x1'])*(g['y2']-g['y1'])-inter)
    return inter/max(1,union)

def box(x1,y1,x2,y2,cls='fly',conf=0.9,is_bg=False):
    return {'x1':x1,'y1':y1,'x2':x2,'y2':y2,'cls':cls,'conf':conf,'is_bg':is_bg}

def gt_box(x1,y1,x2,y2,cls='fly'):
    return {'x1':x1,'y1':y1,'x2':x2,'y2':y2,'cls':cls}

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — bbox_overlap_ratio
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 1. bbox_overlap_ratio ═══")

p = box(0,0,100,100); g = gt_box(0,0,100,100)
check("exact overlap → 1.0", bbox_overlap_ratio(p,g), 1.0)

p = box(50,0,150,100); g = gt_box(0,0,100,100)
# intersection: x=[50,100], y=[0,100] = 50*100=5000; gt_area=10000 → 0.5
check("50% overlap", bbox_overlap_ratio(p,g), 0.5)

p = box(200,200,300,300); g = gt_box(0,0,100,100)
check("no overlap → 0.0", bbox_overlap_ratio(p,g), 0.0)

# pred entirely inside GT (large GT)
p = box(10,10,20,20); g = gt_box(0,0,100,100)
# inter=10*10=100; gt_area=10000 → 0.01
check("tiny pred inside large GT → 0.01", bbox_overlap_ratio(p,g), 0.01)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — center_match
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 2. center_match ═══")

# Criterion 1: GT center inside pred
pred = [box(0,0,100,100)]
gt   = [gt_box(40,40,60,60)]  # GT center=(50,50) inside pred [0,100]
pairs,unp,ung = center_match(pred,gt)
check("GT center in pred → match", pairs, [(0,0)])
check("no unmatched pred", unp, [])
check("no unmatched GT", ung, [])

# Criterion 2: pred center inside GT
pred = [box(40,40,60,60)]
gt   = [gt_box(0,0,100,100)]  # pred center=(50,50) inside GT
pairs,unp,ung = center_match(pred,gt)
check("pred center in GT → match", pairs, [(0,0)])

# Criterion 3: 20% area overlap
pred = [box(0,0,100,100)]
gt   = [gt_box(79,0,200,100)]  # overlap = 21px wide (21% of GT=121*100)
# Actually: GT area = 121*100=12100; intersection = [79,100]*[0,100]=21*100=2100; ratio=2100/12100≈0.174 < 0.20
# So this should NOT match
pairs,unp,ung = center_match(pred,gt)
check("17% overlap → no match", pairs, [])

gt   = [gt_box(75,0,175,100)]   # GT area=100*100=10000; inter=[75,100]*[0,100]=25*100=2500; ratio=0.25 ≥ 0.20
pairs,unp,ung = center_match(pred,gt)
check("25% overlap → match", pairs, [(0,0)])

# No overlap at all
pred = [box(0,0,10,10)]
gt   = [gt_box(100,100,200,200)]
pairs,unp,ung = center_match(pred,gt)
check("no overlap → no match", pairs, [])
check("unmatched pred=[0]", unp, [0])
check("unmatched GT=[0]", ung, [0])

# Greedy: first GT claims the only pred
pred = [box(0,0,100,100)]
gt   = [gt_box(10,10,90,90), gt_box(20,20,80,80)]  # both centers inside pred
pairs,unp,ung = center_match(pred,gt)
check("greedy: first GT gets pred", len(pairs), 1)
check("greedy: one unmatched GT", len(ung), 1)

# Multiple preds and GTs
pred = [box(0,0,50,50), box(100,100,150,150)]
gt   = [gt_box(10,10,40,40), gt_box(110,110,140,140)]
pairs,unp,ung = center_match(pred,gt)
check("2 preds, 2 GTs → 2 pairs", len(pairs), 2)
check("no unmatched", len(unp)+len(ung), 0)

# Empty inputs
pairs,unp,ung = center_match([],[])
check("empty both → empty pairs", pairs, [])

pairs,unp,ung = center_match([box(0,0,10,10)],[])
check("pred with no GT → unmatched pred", unp, [0])

pairs,unp,ung = center_match([],[gt_box(0,0,10,10)])
check("GT with no pred → unmatched GT", ung, [0])

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — evaluate_one_pipeline: perfect detection + classification
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 3. evaluate_one_pipeline — perfect case ═══")

gt = {'img1': [gt_box(0,0,100,100,'fly'), gt_box(200,200,300,300,'butterfly')]}
preds = {'img1': [box(10,10,90,90,'fly'), box(210,210,290,290,'butterfly')]}
r = evaluate_one_pipeline(preds, gt, ['fly','butterfly'], 'test')

check("perfect: det_tp=2", r['det_tp'], 2)
check("perfect: det_fp=0", r['det_fp'], 0)
check("perfect: det_fn=0", r['det_fn'], 0)
check("perfect: det_precision=1.0", r['det_precision'], 1.0)
check("perfect: det_recall=1.0", r['det_recall'], 1.0)
check("perfect: det_f1=1.0", r['det_f1'], 1.0)
check("perfect: cls_accuracy=1.0", r['cls_accuracy'], 1.0)
check("perfect: cls_correct=2", r['cls_correct'], 2)
check("perfect: cls_wrong=0", r['cls_wrong'], 0)
check("perfect: tp_c fly=1", r['tp_c'].get('fly',0), 1)
check("perfect: tp_c butterfly=1", r['tp_c'].get('butterfly',0), 1)
check("perfect: fp_c all 0", sum(r['fp_c'].values()), 0)
check("perfect: fn_c all 0", sum(r['fn_c'].values()), 0)
check("perfect: fn_not_detected=0", r['fn_not_detected'], 0)
check("perfect: fn_detected_as_bg=0", r['fn_detected_as_bg'], 0)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — evaluate_one_pipeline: all missed (no preds)
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 4. evaluate_one_pipeline — all missed ═══")

gt = {'img1': [gt_box(0,0,100,100,'fly'), gt_box(200,200,300,300,'fly')]}
r = evaluate_one_pipeline({}, gt, ['fly'], 'test')

check("all missed: det_tp=0", r['det_tp'], 0)
check("all missed: det_fn=2", r['det_fn'], 2)
check("all missed: det_recall=0.0", r['det_recall'], 0.0)
check("all missed: fn_not_detected=2", r['fn_not_detected'], 2)
check("all missed: fn_detected_as_bg=0", r['fn_detected_as_bg'], 0)
check("all missed: fn_c fly=2", r['fn_c'].get('fly',0), 2)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — evaluate_one_pipeline: all FP (no GT)
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 5. evaluate_one_pipeline — all FP ═══")

preds = {'img1': [box(0,0,100,100,'fly'), box(200,200,300,300,'fly')]}
r = evaluate_one_pipeline(preds, {'img1':[]}, ['fly'], 'test')

check("all FP: det_tp=0", r['det_tp'], 0)
check("all FP: det_fp=2", r['det_fp'], 2)
check("all FP: det_precision=0.0", r['det_precision'], 0.0)
check("all FP: fp_c fly=2", r['fp_c'].get('fly',0), 2)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — evaluate_one_pipeline: wrong classification
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 6. evaluate_one_pipeline — detection TP but wrong class ═══")

# GT=fly, pred=other (matched by position, wrong class)
gt    = {'img1': [gt_box(0,0,100,100,'fly')]}
preds = {'img1': [box(10,10,90,90,'other')]}  # pred center inside GT
r = evaluate_one_pipeline(preds, gt, ['fly','other'], 'test')

check("wrong cls: det_tp=1 (detected)", r['det_tp'], 1)
check("wrong cls: det_fp=0 (no spurious)", r['det_fp'], 0)
check("wrong cls: det_fn=0", r['det_fn'], 0)
check("wrong cls: cls_correct=0", r['cls_correct'], 0)
check("wrong cls: cls_wrong=1", r['cls_wrong'], 1)
check("wrong cls: cls_accuracy=0.0", r['cls_accuracy'], 0.0)
# per-class: fly was detected (det TP) but mislabeled → tp_c[fly]=0, fn_c[fly]=1
check("wrong cls: tp_c fly=0", r['tp_c'].get('fly',0), 0)
check("wrong cls: fn_c fly=1", r['fn_c'].get('fly',0), 1)
# other got a FP (was predicted but wasn't actually there)
check("wrong cls: fp_c other=1", r['fp_c'].get('other',0), 1)
# per-class precision for fly: tp=0, fp=0 → P=0/max(1,0)=0.0
# per-class recall for fly: tp=0, fn=1 → R=0/max(1,1)=0.0
fly_tp=r['tp_c'].get('fly',0); fly_fp=r['fp_c'].get('fly',0); fly_fn=r['fn_c'].get('fly',0)
check("wrong cls: per-class fly P=0.0", fly_tp/max(1,fly_tp+fly_fp), 0.0)
check("wrong cls: per-class fly R=0.0", fly_tp/max(1,fly_tp+fly_fn), 0.0)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — evaluate_one_pipeline: fn_detected_as_bg
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 7. evaluate_one_pipeline — fn_detected_as_bg ═══")

# GT fly, but binary stage rejected it as background (is_bg=True)
# The rejected bbox overlaps the GT → fn_detected_as_bg
gt    = {'img1': [gt_box(0,0,100,100,'fly')]}
preds = {'img1': [box(10,10,90,90,'background', is_bg=True)]}
r = evaluate_one_pipeline(preds, gt, ['fly'], 'test')

check("fn_as_bg: det_tp=0 (no insect preds)", r['det_tp'], 0)
check("fn_as_bg: det_fn=1", r['det_fn'], 1)
check("fn_as_bg: fn_detected_as_bg=1", r['fn_detected_as_bg'], 1)
check("fn_as_bg: fn_not_detected=0", r['fn_not_detected'], 0)
check("fn_as_bg: n_bg_rejected=1", r['n_bg_rejected'], 1)

# GT fly, rejected box does NOT overlap GT → fn_not_detected
preds = {'img1': [box(500,500,600,600,'background', is_bg=True)]}
r = evaluate_one_pipeline(preds, gt, ['fly'], 'test')
check("fn_not_detected: fn_not_detected=1", r['fn_not_detected'], 1)
check("fn_not_detected: fn_detected_as_bg=0", r['fn_detected_as_bg'], 0)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — evaluate_one_pipeline: mixed scenario
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 8. evaluate_one_pipeline — mixed scenario ═══")

# 4 GT insects, 1 correctly detected, 1 wrong class, 1 missed (not detected), 1 false positive
# Scenario: img1 has 3 GT + 4 predictions
gt = {'img1': [
    gt_box(0,0,100,100,'fly'),        # → correctly detected as fly
    gt_box(200,200,300,300,'butterfly'), # → detected but labeled as 'other'
    gt_box(400,400,500,500,'fly'),    # → completely missed (no pred near it)
]}
preds = {'img1': [
    box(10,10,90,90,'fly'),           # matches GT#0 ✓
    box(210,210,290,290,'other'),     # matches GT#1 ✗ (butterfly labeled as other)
    box(700,700,800,800,'fly'),       # FP — no GT near it
]}
r = evaluate_one_pipeline(preds, gt, ['fly','butterfly','other'], 'test')

check("mixed: det_tp=2", r['det_tp'], 2)
check("mixed: det_fp=1", r['det_fp'], 1)
check("mixed: det_fn=1", r['det_fn'], 1)
check("mixed: det_precision=2/3", r['det_precision'], 2/3)
check("mixed: det_recall=2/3", r['det_recall'], 2/3)
check("mixed: det_f1=2/3", r['det_f1'], 2/3)
check("mixed: cls_correct=1", r['cls_correct'], 1)
check("mixed: cls_wrong=1", r['cls_wrong'], 1)
check("mixed: cls_accuracy=0.5", r['cls_accuracy'], 0.5)
# per-class fly: correctly detected GT#0 → tp_c=1; GT#2 missed → fn_c+=1 from ung
check("mixed: tp_c fly=1", r['tp_c'].get('fly',0), 1)
check("mixed: fn_c fly=1 (missed GT#2)", r['fn_c'].get('fly',0), 1)
check("mixed: fp_c fly=1 (FP pred)", r['fp_c'].get('fly',0), 1)
# per-class butterfly: GT#1 detected but labeled other → tp_c=0, fn_c=1 (misclassified)
check("mixed: tp_c butterfly=0", r['tp_c'].get('butterfly',0), 0)
check("mixed: fn_c butterfly=1 (misclassified)", r['fn_c'].get('butterfly',0), 1)
# per-class other: got a FP (predicted other but GT was butterfly)
check("mixed: fp_c other=1", r['fp_c'].get('other',0), 1)
check("mixed: fn_not_detected=1 (GT#2)", r['fn_not_detected'], 1)
check("mixed: fn_detected_as_bg=0", r['fn_detected_as_bg'], 0)
# P/R/F1 for fly class:
fly_tp=r['tp_c'].get('fly',0); fly_fp=r['fp_c'].get('fly',0); fly_fn=r['fn_c'].get('fly',0)
fly_P = fly_tp/max(1,fly_tp+fly_fp); fly_R = fly_tp/max(1,fly_tp+fly_fn)
check("mixed: fly_P=0.5", fly_P, 0.5)
check("mixed: fly_R=0.5", fly_R, 0.5)
# rows: 2 tp + 1 fp + 1 fn_not_detected = 4
check("mixed: 4 rows", len(r['rows']), 4)
tp_rows = [ro for ro in r['rows'] if ro['match']=='tp']
check("mixed: 2 tp rows", len(tp_rows), 2)
fn_rows = [ro for ro in r['rows'] if ro['match']=='fn_not_detected']
check("mixed: 1 fn_not_detected row", len(fn_rows), 1)
fn_gt_cls = fn_rows[0]['gt_cls']
check("mixed: missed GT is fly", fn_gt_cls, 'fly')

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — per-plot metrics match global (consistency check)
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 9. per-plot ↔ global consistency ═══")

CLASSES = ['bumblebee', 'fly', 'butterfly', 'other']
gt_img = {
    'img1': [
        gt_box(0,0,100,100,'fly'),
        gt_box(200,200,300,300,'butterfly'),
        gt_box(400,400,500,500,'other'),
    ],
    'img2': [
        gt_box(0,0,100,100,'bumblebee'),
        gt_box(200,200,300,300,'fly'),
    ],
}
preds_img = {
    'img1': [
        box(10,10,90,90,'fly'),           # fly ✓
        box(210,210,290,290,'other'),     # butterfly → other ✗
        box(410,410,490,490,'other'),     # other ✓
    ],
    'img2': [
        box(10,10,90,90,'bumblebee'),     # bumblebee ✓
        box(800,800,900,900,'fly'),       # FP
    ],
    # fly in img2 GT#1 → completely missed
}

r_global = evaluate_one_pipeline(preds_img, gt_img, CLASSES, 'test')

# aggregate per-plot over all images (simulating the plot = whole image set)
pp = perplot_metrics(preds_img, gt_img, CLASSES)

for c in CLASSES:
    tp_g = r_global['tp_c'].get(c,0); fp_g = r_global['fp_c'].get(c,0); fn_g = r_global['fn_c'].get(c,0)
    tp_p = pp[c]['tp'];               fp_p = pp[c]['fp'];               fn_p = pp[c]['fn']
    check(f"per-plot vs global tp_c[{c}]: {tp_g}=={tp_p}", tp_g == tp_p, True)
    check(f"per-plot vs global fp_c[{c}]: {fp_g}=={fp_p}", fp_g == fp_p, True)
    check(f"per-plot vs global fn_c[{c}]: {fn_g}=={fn_p}", fn_g == fn_p, True)

# misclassification label correctness: butterfly detected as other → errors['butterfly']={'other':1}
check("per-plot: butterfly→other error recorded", pp['butterfly']['errors'].get('other',0), 1)
check("per-plot: fly has no errors (correctly detected)", len(pp['fly']['errors']), 0)
check("per-plot: bumblebee has no errors", len(pp['bumblebee']['errors']), 0)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10 — combined_recall
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 10. combined_recall (crop + YOLO) ═══")

gt_c = {'img1': [gt_box(0,0,100,100,'fly'), gt_box(200,200,300,300,'fly'), gt_box(400,400,500,500,'fly')]}
# crop finds GT#0 and GT#1; YOLO finds GT#1 and GT#2
crop_p = {'img1': [box(10,10,90,90,'fly'), box(210,210,290,290,'fly')]}
yolo_p = {'img1': [box(210,210,290,290,'fly'), box(410,410,490,490,'fly')]}

res = combined_recall(crop_p, yolo_p, gt_c)
check("combined: both=1 (GT#1 by both)", res['both'], 1)
check("combined: crop_only=1 (GT#0)", res['crop_only'], 1)
check("combined: yolo_only=1 (GT#2)", res['yolo_only'], 1)
check("combined: neither=0", res['neither'], 0)
check("combined: crop_recall=2/3", res['crop_recall'], 2/3)
check("combined: yolo_recall=2/3", res['yolo_recall'], 2/3)
check("combined: combined_recall=3/3=1.0", res['combined_recall'], 1.0)

# all missed
res2 = combined_recall({}, {}, gt_c)
check("all missed: combined_recall=0", res2['combined_recall'], 0.0)
check("all missed: neither=3", res2['neither'], 3)

# crop gets all, YOLO gets nothing
crop_all = {'img1': [box(10,10,90,90,'fly'), box(210,210,290,290,'fly'), box(410,410,490,490,'fly')]}
res3 = combined_recall(crop_all, {}, gt_c)
check("crop-only: combined=crop_recall=1.0", res3['combined_recall'], 1.0)
check("crop-only: yolo_only=0", res3['yolo_only'], 0)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 11 — confidence threshold filtering
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 11. conf threshold filtering ═══")

# Threshold analysis logic: sort by conf desc, compute cumulative P/R
def threshold_sweep(rows):
    """Simulate PR curve computation from Cell 20."""
    det_tp = rows[0]['det_tp'] + rows[0]['det_fn']  # total GT = tp + fn
    dets = sorted(
        [(ro['conf'], ro['match'] == 'tp')
         for ro in rows[0]['rows'] if ro['match'] in ('tp','fp')],
        key=lambda x: -x[0])
    tp_=fp_=0; precisions=[]; recalls=[]
    for conf, is_tp in dets:
        if is_tp: tp_+=1
        else: fp_+=1
        p  = tp_/max(1,tp_+fp_)
        rc = tp_/max(1,det_tp)
        precisions.append(p); recalls.append(rc)
    return precisions, recalls

# Simple case: 2 TPs at high conf, 1 FP at low conf
gt_thr = {'img1': [gt_box(0,0,100,100,'fly'), gt_box(200,200,300,300,'fly')]}
preds_thr = {'img1': [
    box(10,10,90,90,'fly',conf=0.9),    # TP high conf
    box(210,210,290,290,'fly',conf=0.8),# TP medium conf
    box(700,700,800,800,'fly',conf=0.2),# FP low conf
]}
r_thr = evaluate_one_pipeline(preds_thr, gt_thr, ['fly'], 'test')
prs, rcs = threshold_sweep([r_thr])

# After processing all 3 dets (desc order: 0.9 TP, 0.8 TP, 0.2 FP):
# Step 1: conf=0.9 TP → P=1/1=1.0, R=1/2=0.5
# Step 2: conf=0.8 TP → P=2/2=1.0, R=2/2=1.0
# Step 3: conf=0.2 FP → P=2/3, R=2/2=1.0
check("thr sweep: P at step 1 = 1.0", prs[0], 1.0)
check("thr sweep: R at step 1 = 0.5", rcs[0], 0.5)
check("thr sweep: P at step 2 = 1.0", prs[1], 1.0)
check("thr sweep: R at step 2 = 1.0", rcs[1], 1.0)
check("thr sweep: P at step 3 = 2/3", prs[2], 2/3)
check("thr sweep: R at step 3 = 1.0", rcs[2], 1.0)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 12 — multi-image aggregation correctness
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 12. multi-image aggregation ═══")

gt_m = {
    'img1': [gt_box(0,0,100,100,'fly')],
    'img2': [gt_box(0,0,100,100,'fly')],
    'img3': [gt_box(0,0,100,100,'fly')],
}
preds_m = {
    'img1': [box(10,10,90,90,'fly')],   # TP
    'img2': [],                           # miss
    # img3: no preds at all
}
r = evaluate_one_pipeline(preds_m, gt_m, ['fly'], 'test')
check("multi: det_tp=1", r['det_tp'], 1)
check("multi: det_fn=2", r['det_fn'], 2)
check("multi: det_recall=1/3", r['det_recall'], 1/3)
check("multi: fn_c fly=2", r['fn_c'].get('fly',0), 2)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 13 — no-bb exclusion consistency
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 13. bumblebee exclusion (gt_no_bb filter) ═══")

gt_full = {'img1': [
    gt_box(0,0,100,100,'bumblebee'),
    gt_box(200,200,300,300,'fly'),
]}
gt_no_bb = {'img1': [b for b in gt_full['img1'] if b['cls'] != 'bumblebee']}
preds_nb = {'img1': [
    box(10,10,90,90,'bumblebee'),     # matches GT bumblebee
    box(210,210,290,290,'fly'),       # matches GT fly
]}
r_full = evaluate_one_pipeline(preds_nb, gt_full, ['bumblebee','fly'], 'full')
r_nobb = evaluate_one_pipeline(preds_nb, gt_no_bb, ['fly'], 'nobb')

# With BB excluded: the bumblebee prediction becomes FP, fly is TP
check("no_bb: det_tp=1 (only fly GT)", r_nobb['det_tp'], 1)
check("no_bb: det_fp=1 (bb pred is FP vs fly-only GT)", r_nobb['det_fp'], 1)
check("no_bb: fn_c fly=0", r_nobb['fn_c'].get('fly',0), 0)
check("full: det_tp=2", r_full['det_tp'], 2)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 14 — iou_match (Cell 35)
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 14. iou_match ═══")

def iou_match(pred_boxes, gt_boxes, iou_thresh=0.50):
    def _iou(p, g):
        ix1=max(p['x1'],g['x1']); iy1=max(p['y1'],g['y1'])
        ix2=min(p['x2'],g['x2']); iy2=min(p['y2'],g['y2'])
        inter=max(0,ix2-ix1)*max(0,iy2-iy1)
        union=((p['x2']-p['x1'])*(p['y2']-p['y1'])+(g['x2']-g['x1'])*(g['y2']-g['y1'])-inter)
        return inter/max(1,union)
    candidates=sorted((-_iou(p,g),pi,gi) for pi,p in enumerate(pred_boxes)
                       for gi,g in enumerate(gt_boxes) if _iou(p,g)>=iou_thresh)
    mp=set(); mg=set(); pairs=[]
    for _,pi,gi in candidates:
        if pi not in mp and gi not in mg: pairs.append((pi,gi)); mp.add(pi); mg.add(gi)
    return (pairs,[i for i in range(len(pred_boxes)) if i not in mp],
                  [i for i in range(len(gt_boxes)) if i not in mg])

# Exact overlap → IoU=1.0 ≥ 0.5 → match
pairs,unp,ung = iou_match([box(0,0,100,100)],[gt_box(0,0,100,100)])
check("iou exact overlap → match", pairs, [(0,0)])

# 50% overlap: IoU=50*100/(100*100+100*100-50*100)=5000/15000=0.333 < 0.5 → no match
pairs,unp,ung = iou_match([box(50,0,150,100)],[gt_box(0,0,100,100)])
check("iou 33% → no match at thresh=0.5", pairs, [])

# 75% overlap: pred=[0,100], GT=[25,125] inter=[25,100]=75*100=7500; union=10000+10000-7500=12500; IoU=0.6
pairs,unp,ung = iou_match([box(0,0,100,100)],[gt_box(25,0,125,100)])
check("iou 60% → match at thresh=0.5", pairs, [(0,0)])

# Greedy: higher-IoU match wins
p1=box(0,0,100,100); p2=box(10,10,90,90)  # p2 has higher IoU with GT
pairs,unp,ung = iou_match([p1,p2],[gt_box(0,0,100,100)])
# p2 IoU: 80*80/(100*100+80*80-80*80)=6400/10000=0.64 > p1 IoU=1.0... wait p2 is inside p1 and GT
# p1 IoU vs GT: exact=1.0; p2 IoU vs GT=(80*80)/(10000+6400-6400)=6400/10000=0.64
# p1 gets it since IoU=1.0 > 0.64
check("iou greedy: higher-IoU pred wins", pairs[0][0] if pairs else -1, 0)

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 15 — Cell 27 per-class stats: class-specific matching
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 15. Cell 27 combined per-class — class-specific ═══")

def combined_perclass(crop_preds, yolo_preds, gt, gt_classes):
    """Cell 27 per-class logic AFTER fix (class-specific)."""
    cls_gt   = {c:0 for c in gt_classes}
    cls_crop = {c:0 for c in gt_classes}
    cls_yolo = {c:0 for c in gt_classes}
    cls_both = {c:0 for c in gt_classes}
    cls_union= {c:0 for c in gt_classes}
    crop_only=0; yolo_only=0; both=0; neither=0

    for img_p, gt_boxes in gt.items():
        if not gt_boxes: continue
        crop_ins = [p for p in crop_preds.get(img_p,[]) if not p.get('is_bg')]
        yolo_ins = yolo_preds.get(img_p, [])
        crop_pairs,_,_ = center_match(crop_ins, gt_boxes)
        yolo_pairs,_,_ = center_match(yolo_ins, gt_boxes)
        crop_det_gt   = {gi for _,gi in crop_pairs}
        yolo_det_gt   = {gi for _,gi in yolo_pairs}
        crop_gi_to_pi = {gi:pi for pi,gi in crop_pairs}
        yolo_gi_to_pi = {gi:pi for pi,gi in yolo_pairs}

        for gi, g in enumerate(gt_boxes):
            gc = g['cls']
            cls_gt[gc] += 1
            in_crop = gi in crop_det_gt
            in_yolo = gi in yolo_det_gt
            _cp = crop_gi_to_pi.get(gi)
            in_crop_cls = _cp is not None and crop_ins[_cp]['cls'] == gc
            _yp = yolo_gi_to_pi.get(gi)
            in_yolo_cls = _yp is not None and yolo_ins[_yp]['cls'] == gc
            if in_crop_cls: cls_crop[gc] += 1
            if in_yolo_cls: cls_yolo[gc] += 1
            if in_crop_cls or in_yolo_cls: cls_union[gc] += 1
            if in_crop_cls and in_yolo_cls: cls_both[gc] += 1
            if in_crop and in_yolo: both += 1
            elif in_crop: crop_only += 1
            elif in_yolo: yolo_only += 1
            else: neither += 1

    return {'cls_crop':cls_crop,'cls_yolo':cls_yolo,'cls_union':cls_union,
            'cls_both':cls_both,'cls_gt':cls_gt,
            'crop_only':crop_only,'yolo_only':yolo_only,'both':both,'neither':neither}

# Scenario: YOLO predicts "fly" at bumblebee location → should NOT count for bumblebee
gt_bb = {'img1': [gt_box(0,0,100,100,'bumblebee')]}
crop_bb = {'img1': [box(10,10,90,90,'bumblebee')]}  # crop correctly says bumblebee
yolo_bb = {'img1': [box(10,10,90,90,'fly')]}         # YOLO says fly (bbox overlaps GT bumblebee)

res = combined_perclass(crop_bb, yolo_bb, gt_bb, ['bumblebee','fly'])

check("cls15: YOLO 'fly' at bumblebee → cls_yolo[bumblebee]=0",
      res['cls_yolo']['bumblebee'], 0)
check("cls15: YOLO 'fly' at bumblebee → cls_yolo[fly]=0 (GT is bumblebee, not fly)",
      res['cls_yolo'].get('fly',0), 0)
check("cls15: crop correctly predicts bumblebee → cls_crop[bumblebee]=1",
      res['cls_crop']['bumblebee'], 1)
check("cls15: union bumblebee = 1 (crop got it right)",
      res['cls_union']['bumblebee'], 1)
check("cls15: overall both=1 (class-agnostic, bbox overlaps)",
      res['both'], 1)  # location-agnostic total: yes both bboxes cover GT

# Scenario: both pipelines correctly predict fly → both count
gt_fly = {'img1': [gt_box(0,0,100,100,'fly')]}
crop_fly = {'img1': [box(10,10,90,90,'fly')]}
yolo_fly = {'img1': [box(5,5,95,95,'fly')]}

res2 = combined_perclass(crop_fly, yolo_fly, gt_fly, ['fly'])
check("cls15: both correctly predict fly → cls_crop[fly]=1", res2['cls_crop']['fly'], 1)
check("cls15: both correctly predict fly → cls_yolo[fly]=1", res2['cls_yolo']['fly'], 1)
check("cls15: both correctly predict fly → cls_both[fly]=1", res2['cls_both']['fly'], 1)
check("cls15: both correctly predict fly → cls_union[fly]=1", res2['cls_union']['fly'], 1)

# Scenario: crop detects fly correctly, YOLO detects fly as 'other' → YOLO doesn't get per-class credit
crop_f = {'img1': [box(10,10,90,90,'fly')]}
yolo_f = {'img1': [box(10,10,90,90,'other')]}  # wrong label
gt_f   = {'img1': [gt_box(0,0,100,100,'fly')]}

res3 = combined_perclass(crop_f, yolo_f, gt_f, ['fly','other'])
check("cls15: crop fly correct → cls_crop[fly]=1", res3['cls_crop']['fly'], 1)
check("cls15: YOLO 'other' at fly location → cls_yolo[fly]=0", res3['cls_yolo']['fly'], 0)
check("cls15: union fly=1 (crop covers it)", res3['cls_union']['fly'], 1)
check("cls15: cls_both fly=0 (YOLO didn't classify correctly)", res3['cls_both']['fly'], 0)
check("cls15: overall both=1 (location-agnostic total)", res3['both'], 1)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 16 — Cell 39 complementarity: class-specific matching
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 16. Cell 39 complementarity — class-specific ═══")

KEYS = ('both','crop_only','yolo_only','neither')

def complementarity_perclass(crop_preds, yolo_preds, gt, gt_classes):
    """Cell 39 complementarity logic AFTER fix (class-specific)."""
    per_cls = {c: {k:0 for k in KEYS} for c in gt_classes + ['_total']}
    for img_p, gt_boxes in gt.items():
        ci = [p for p in crop_preds.get(img_p,[]) if not p.get('is_bg')]
        yi = yolo_preds.get(img_p, [])
        c_pairs,_,_ = center_match(ci, gt_boxes)
        y_pairs,_,_ = center_match(yi, gt_boxes)
        c_gi_cls = {gi:ci[pi]['cls'] for pi,gi in c_pairs}
        y_gi_cls = {gi:yi[pi]['cls'] for pi,gi in y_pairs}
        for gi, gb in enumerate(gt_boxes):
            gc = gb['cls']
            in_c = gi in c_gi_cls and c_gi_cls[gi] == gc
            in_y = gi in y_gi_cls and y_gi_cls[gi] == gc
            key = ('both' if (in_c and in_y) else
                   'crop_only' if in_c else
                   'yolo_only' if in_y else 'neither')
            per_cls[gc][key] += 1
            per_cls['_total'][key] += 1
    return per_cls

# YOLO 'fly' at bumblebee location → 'neither' for bumblebee (not 'yolo_only')
gt_c = {'img1': [gt_box(0,0,100,100,'bumblebee'), gt_box(200,200,300,300,'fly')]}
crop_c = {'img1': [box(210,210,290,290,'fly')]}              # crop: fly ✓
yolo_c = {'img1': [box(10,10,90,90,'fly'),                   # YOLO at bumblebee → 'fly' ✗
                   box(210,210,290,290,'fly')]}              # YOLO at fly → 'fly' ✓

pc = complementarity_perclass(crop_c, yolo_c, gt_c, ['bumblebee','fly'])

check("cls16: bumblebee 'neither' (YOLO wrong label, crop missed)", pc['bumblebee']['neither'], 1)
check("cls16: bumblebee 'yolo_only' = 0 (YOLO labeled it fly)", pc['bumblebee']['yolo_only'], 0)
check("cls16: fly 'both' = 1 (both found fly correctly)", pc['fly']['both'], 1)
check("cls16: _total 'both'=1, 'neither'=1", pc['_total']['both'], 1)
check("cls16: _total 'neither'=1", pc['_total']['neither'], 1)

# both pipelines correct on everything
gt_c2 = {'img1': [gt_box(0,0,100,100,'fly'), gt_box(200,200,300,300,'butterfly')]}
crop_c2 = {'img1': [box(10,10,90,90,'fly'), box(210,210,290,290,'butterfly')]}
yolo_c2 = {'img1': [box(10,10,90,90,'fly'), box(210,210,290,290,'butterfly')]}

pc2 = complementarity_perclass(crop_c2, yolo_c2, gt_c2, ['fly','butterfly'])
check("cls16: fly 'both'=1 (both correct)", pc2['fly']['both'], 1)
check("cls16: butterfly 'both'=1", pc2['butterfly']['both'], 1)
check("cls16: no crop_only/yolo_only/neither", pc2['_total']['crop_only']+pc2['_total']['yolo_only']+pc2['_total']['neither'], 0)

# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'═'*60}")
print(f"  Results: {PASS} passed, {FAIL} failed, {PASS+FAIL} total")
print(f"{'═'*60}")
import sys; sys.exit(0 if FAIL == 0 else 1)
