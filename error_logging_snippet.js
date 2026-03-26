// =====================================================
// 휙 에러 로그 수집 — 각 HTML 파일의 <script> 상단에 추가
// =====================================================

// 페이지명 (파일마다 변경)
const PAGE_NAME = 'card_generator'; // 또는 'my_cards', 'property_view', 'select_template'

// 에러 로그 전송
async function logError(action, errorMsg, detail = null) {
    try {
        await supabaseClient.from('error_logs').insert({
            user_id: currentUser?.id || null,
            page: PAGE_NAME,
            action: action,
            error_msg: String(errorMsg).slice(0, 500),
            error_detail: detail ? JSON.stringify(detail).slice(0, 2000) : null
        });
    } catch(e) {
        // 로그 저장 자체가 실패해도 서비스에 영향 없도록
        console.warn('[휙 로그 실패]', e);
    }
}

// =====================================================
// 사용 예시 — 기존 try-catch에 한 줄만 추가
// =====================================================

// 예시 1) GPT 파싱 실패
// 기존:
//   catch(e) { alert('파싱 실패'); }
// 변경:
//   catch(e) { logError('gpt_parse', e.message, { input: inputText.slice(0,300) }); alert('파싱 실패'); }

// 예시 2) 카드 저장 실패  
//   catch(e) { logError('save_card', e.message, { cardId: linkId }); alert('저장 실패'); }

// 예시 3) 사진 업로드 실패
//   catch(e) { logError('upload_photo', e.message, { cardId, photoIndex: i }); }

// 예시 4) 카카오 공유 실패
//   catch(e) { logError('kakao_share', e.message, { cardId }); }

// 예시 5) 벡터 검색 실패
//   catch(e) { logError('vector_search', e.message, { query: searchQuery }); }

// 예시 6) 프로필 저장 실패
//   catch(e) { logError('save_profile', e.message); alert('프로필 저장 실패'); }

// =====================================================
// 전역 에러 캐치 (예상 못한 에러도 수집)
// =====================================================
window.addEventListener('error', (e) => {
    logError('unhandled_error', e.message, { 
        file: e.filename, 
        line: e.lineno, 
        col: e.colno 
    });
});

window.addEventListener('unhandledrejection', (e) => {
    logError('unhandled_promise', String(e.reason).slice(0, 500));
});
