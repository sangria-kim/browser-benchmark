"""Build a source-only flag archive from cached official commits and unified diffs.
Usage: python3 scripts/build_flag_archive.py CACHE OUTPUT
CACHE: commits-cache.json, baseline.cc, end.cc, diffs/<sha>.patch.
Refuses missing/truncated/out-of-order diffs and a final snapshot mismatch.
Caches are private working inputs, never publication artifacts.
"""
import collections, hashlib, json, re, sys
from pathlib import Path

def apply_diff(text, diff):
    old=text.splitlines(keepends=True); out=[]; pos=0
    lines=diff.splitlines(keepends=True); i=0
    while i<len(lines):
        m=re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@',lines[i])
        if not m: i+=1; continue
        start=int(m[1])-1 if int(m[2] or 1) else int(m[1]); oc=int(m[2] or 1); nc=int(m[4] or 1)
        assert start>=pos, 'overlapping hunk'
        out.extend(old[pos:start]);pos=start;i+=1;a=b=0
        while i<len(lines) and (a<oc or b<nc):
            line=lines[i];i+=1
            if line.startswith('\\'): continue
            assert line and line[0] in ' +-','bad hunk'
            if line[0] in ' -':
                assert pos<len(old) and old[pos]==line[1:], f'hunk mismatch line {pos+1}'
                pos+=1;a+=1
            if line[0] in ' +':out.append(line[1:]);b+=1
        assert (a,b)==(oc,nc),'truncated hunk'
    out.extend(old[pos:]);return ''.join(out)

def entries(text):
    section=text.split('const FeatureEntry kFeatureEntries[] = {',1)[1].split('\n};',1)[0]
    result={}
    for m in re.finditer(r'^    \{"([a-z0-9][a-z0-9-]*)"\s*,',section,re.M):
        depth=0
        for t in re.finditer(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/|[{}]',section[m.start():]):
            if t[0]=='{':depth+=1
            elif t[0]=='}':
                depth-=1
                if depth==0:
                    result[m[1]]=section[m.start():m.start()+t.end()];break
    return result

def build(cache, output):
    def write(p,data):
        p=output/p;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n' if not isinstance(data,str) else data)
    commits=json.loads((cache/'commits-cache.json').read_text())
    assert len({c['sha'] for c in commits})==len(commits)
    text=(cache/'baseline.cc').read_text();initial=entries(text);current=initial
    events=[];byflag=collections.defaultdict(list)
    for c in reversed(commits):
        patch=(cache/'diffs'/f"{c['sha']}.patch").read_text()
        text=apply_diff(text,patch);after=entries(text)
        changes=[]
        for fid in sorted(current.keys()|after.keys()):
            if current.get(fid)==after.get(fid):continue
            action='added' if fid not in current else 'removed' if fid not in after else 'modified'
            change={'flag_id':fid,'action':action,'source_os_masks':sorted(set(re.findall(r'\bkOs\w+',after.get(fid,current.get(fid,'')))))}
            changes.append(change)
        event={'event_id':'chrome-about-flags-'+c['sha'],'source_revision':c['sha'],'committed_at':c['commit']['committer']['date'],'source_url':'https://chromium.googlesource.com/chromium/src/+/'+c['sha']+'/chrome/browser/about_flags.cc','diff_url':'https://github.com/chromium/chromium/commit/'+c['sha'],'changes':changes,'mapping_status':'direct_entries_changed' if changes else 'no_direct_entry_change','verification_status':'source_only','installed_availability':'unknown','selection_status':'pending_verification'}
        events.append(event)
        for change in changes:byflag[change['flag_id']].append((event,change))
        current=after
    assert text==(cache/'end.cc').read_text(),'final snapshot mismatch'
    months=collections.defaultdict(list)
    for e in events:months[e['committed_at'][:7]].append(e)
    counts=collections.Counter(c['action'] for e in events for c in e['changes'])
    manifest={'schema_version':1,'period_start':'2026-06-01T00:00:00Z','period_end':'2026-10-29T15:00:00Z','scope':'commits touching chrome/browser/about_flags.cc only','baseline_revision':commits[-1]['parents'][0]['sha'],'end_revision':commits[0]['sha'],'commit_count':len(events),'flags_with_direct_entry_changes':len(byflag),'change_counts':dict(counts),'commits_without_direct_entry_change':sum(not e['changes'] for e in events),'baseline_sha256':hashlib.sha256((cache/'baseline.cc').read_bytes()).hexdigest(),'end_sha256':hashlib.sha256(text.encode()).hexdigest(),'validation':'All diffs replayed from baseline; final content exactly matches official end snapshot.','limitations':['Only literal IDs in kFeatureEntries are mapped. Symbolic IDs, external definitions and preprocessor-only changes require manual review.','Changes solely to flag_descriptions.cc or flag-metadata.json are not covered.','An addition is a registration within this window, not proof of first-ever introduction.','No installed Chrome builds were tested.']}
    write(Path('experiments/chrome/manifest.json'),manifest)
    for month,es in months.items():
        write(Path(f'experiments/chrome/monthly/{month}.json'),{'schema_version':1,'events':es})
        rows=['# '+month+' Chrome flag 변경\n','commit 날짜는 UTC입니다. 설치본 출시일이 아닙니다.\n','| Commit | 날짜 | 직접 변경 flag 수 |','| --- | --- | --- |']
        rows += [f"| [{e['source_revision'][:12]}]({e['diff_url']}) | {e['committed_at'][:10]} | {len(e['changes'])} |" for e in es]
        write(Path(f'experiments/chrome/monthly/{month}.md'),'\n'.join(rows)+'\n')
    for fid,history in byflag.items():
        rows=[f'# {fid}\n','검증 상태: **소스 관찰만 완료**. 설치본 노출·동작·최소 Chrome 버전은 미확인입니다. PM 선별은 검증 대기입니다.\n',f"- 기간 시작 snapshot에 등록: {'예' if fid in initial else '아니요'}",f"- 기간 종료 snapshot에 등록: {'예' if fid in current else '아니요'}",'- 추가는 기간 내 등록/재등록을 뜻하며 최초 출시를 보장하지 않습니다. 삭제는 정식 출시·철회의 증거가 아닙니다.','- OS mask는 소스 표현이며 실제 빌드 조건·지원 범위는 별도 확인이 필요합니다.\n','| UTC 날짜 | 사건 | OS mask | 공식 diff |','| --- | --- | --- | --- |']
        rows += [f"| {e['committed_at'][:10]} | {ch['action']} | {', '.join(ch['source_os_masks']) or 'unknown'} | [{e['source_revision'][:12]}]({e['diff_url']}) |" for e,ch in history]
        rows+=['\n[전체 목록](README.md)\n']
        write(Path(f'experiments/chrome/{fid}.md'),'\n'.join(rows))
    rows=['# Chrome flags: 2026년 6월 이후\n',f"2026-06-01 00:00 UTC부터 2026-10-29 15:00 UTC까지 about_flags.cc 변경 **{len(events):,} commit**, 직접 등록부 변경 **{len(byflag):,} flag ID**를 보관합니다.\n",'전체 diff를 시작 snapshot에 순서대로 적용했고 종료 snapshot과 바이트 내용을 대조했습니다. 세부 수치·revision·검증 범위는 [manifest](manifest.json)를 확인하세요.\n','## 범위와 한계\n','등록부의 literal flag ID에 대한 추가·수정·삭제입니다. 외부 상수·전처리 조건 등 직접 연결하지 못한 commit도 월별 JSON에 보존합니다. 설명·만료 파일만 단독 수정한 commit은 아직 수집하지 않았습니다. 따라서 전체 Chrome 실험 이력 수집 완료를 뜻하지 않습니다. 모든 항목은 설치본 미검증·PM 선별 대기입니다.\n','## 월별 이력\n']
    rows += [f'- [{m}]({"monthly/"+m+".md"}) · [JSON](monthly/{m}.json) · {len(es)} commit' for m,es in sorted(months.items())]
    rows+=['\n## Flag별 이력\n']+[f'- [{fid}]({fid}.md)' for fid in sorted(byflag)]
    write(Path('experiments/chrome/README.md'),'\n'.join(rows)+'\n');print(json.dumps(manifest,ensure_ascii=False))

if __name__=='__main__':build(Path(sys.argv[1]),Path(sys.argv[2]))
