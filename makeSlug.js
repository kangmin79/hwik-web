/**
 * makeSlug.js — 단지/동 slug 생성 (단일 소스)
 * Python slug_utils.py와 100% 동기화된 로직.
 * danji.html, dong.html, gu.html, ranking.html에서 <script src="/makeSlug.js"> 로 사용.
 */
var _RM={'서울특별시':'서울','인천광역시':'인천','부산광역시':'부산','대구광역시':'대구','광주광역시':'광주','대전광역시':'대전','울산광역시':'울산','세종특별자치시':'세종','경기도':'경기','강원특별자치도':'강원','충청북도':'충북','충청남도':'충남','전북특별자치도':'전북','전라남도':'전남','경상북도':'경북','경상남도':'경남','제주특별자치도':'제주','서울':'서울','인천':'인천','부산':'부산','대구':'대구','광주':'광주','대전':'대전','울산':'울산','세종':'세종','경기':'경기','강원':'강원','충북':'충북','충남':'충남','전북':'전북','전남':'전남','경북':'경북','경남':'경남','제주':'제주'};
var _MC=new Set(['서울','인천','부산','대구','광주','대전','울산']);
function _cl(s){return(s||'').replace(/[^\w가-힣]/g,'-').replace(/-+/g,'-').replace(/^-|-$/g,'');}
function makeSlug(name,loc,did,addr){var a=(addr||'').split(/\s+/),r=a[0]?(_RM[a[0]]||''):'',p=[];if(r){p.push(r);if(_MC.has(r)){if(a[1]&&(a[1].endsWith('구')||a[1].endsWith('군')))p.push(a[1].endsWith('군')?a[1].replace(/군$/,''):a[1]);}else if(r!=='세종'){if(a[1])p.push(a[1].replace(/(시|군)$/,''));if(a[2]&&a[2].endsWith('구'))p.push(a[2]);}}else{var l=(loc||'').split(' ');if(l[0])p.push(_cl(l[0]));}var ls=(loc||'').split(' ');if(ls.length>=2)ls.slice(1).forEach(function(d){p.push(_cl(d));});if(did&&(did.startsWith('offi-')||did.startsWith('apt-'))){p.push(did);}else{p.push(_cl(name));if(did)p.push(did);}return p.filter(Boolean).map(function(x){return _cl(x);}).join('-');}
