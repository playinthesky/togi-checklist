/**
 * 청토지 보수교육 체크리스트 - Google Sheets 연동 스크립트
 *
 * [설치 방법]
 * 1. 새 구글 시트를 만듭니다
 * 2. 확장 프로그램 > Apps Script 클릭
 * 3. 이 코드를 전체 복사하여 붙여넣기
 * 4. 배포 > 새 배포 > 유형: 웹 앱 선택
 *    - 실행 계정: 본인
 *    - 액세스 권한: 모든 사용자
 * 5. 배포 후 나오는 URL을 복사하여 관리자 대시보드에 붙여넣기
 */

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var ss = SpreadsheetApp.getActiveSpreadsheet();

    // === 1. 전체 현황 시트 ===
    var overviewSheet = getOrCreateSheet(ss, '전체 현황');
    overviewSheet.clear();

    // 제목
    overviewSheet.getRange('A1').setValue(data.title || '청토지 보수교육 체크리스트');
    overviewSheet.getRange('A1').setFontSize(14).setFontWeight('bold');
    overviewSheet.getRange('A2').setValue('마지막 동기화: ' + data.exportedAt);
    overviewSheet.getRange('A2').setFontColor('#888888');

    // 전체 통계
    overviewSheet.getRange('A4:B4').setValues([['전체 진행률', data.overallPercent + '%']]);
    overviewSheet.getRange('A5:B5').setValues([['완료 항목', data.doneChecks + ' / ' + data.totalChecks]]);
    overviewSheet.getRange('A6:B6').setValues([['체크리스트 항목 수', data.totalItems]]);
    overviewSheet.getRange('A7:B7').setValues([['참여 지회 수', data.staffCount]]);
    overviewSheet.getRange('A4:A7').setFontWeight('bold');

    // 지회별 진행 현황
    overviewSheet.getRange('A9').setValue('지회별 진행 현황');
    overviewSheet.getRange('A9').setFontSize(12).setFontWeight('bold');

    var staffHeaders = [['지회', '담당자', '확인 항목', '전체 항목', '진행률']];
    overviewSheet.getRange('A10:E10').setValues(staffHeaders);
    overviewSheet.getRange('A10:E10').setFontWeight('bold').setBackground('#1a365d').setFontColor('#ffffff');

    var staffRows = data.staffStats.map(function(s) {
      return [s.name, s.contact_name || '', s.checked, s.total, s.percent + '%'];
    });
    if (staffRows.length > 0) {
      overviewSheet.getRange(11, 1, staffRows.length, 5).setValues(staffRows);
    }

    // 카테고리별 현황
    var catStartRow = 11 + staffRows.length + 2;
    overviewSheet.getRange(catStartRow, 1).setValue('카테고리별 현황');
    overviewSheet.getRange(catStartRow, 1).setFontSize(12).setFontWeight('bold');

    var catHeaders = [['카테고리', '항목 수', '완료', '전체', '진행률']];
    overviewSheet.getRange(catStartRow + 1, 1, 1, 5).setValues(catHeaders);
    overviewSheet.getRange(catStartRow + 1, 1, 1, 5).setFontWeight('bold').setBackground('#2b6cb0').setFontColor('#ffffff');

    var catRows = data.catStats.map(function(c) {
      return [c.name, c.itemCount, c.doneChecks, c.totalChecks, c.percent + '%'];
    });
    if (catRows.length > 0) {
      overviewSheet.getRange(catStartRow + 2, 1, catRows.length, 5).setValues(catRows);
    }

    // 컬럼 너비 자동 조절
    overviewSheet.autoResizeColumns(1, 5);

    // === 2. 품목별 상세 시트 ===
    var detailSheet = getOrCreateSheet(ss, '품목별 상세');
    detailSheet.clear();

    var staffNames = data.staffNames || [];
    var detailHeaders = ['카테고리', '품목'].concat(staffNames);
    detailSheet.getRange(1, 1, 1, detailHeaders.length).setValues([detailHeaders]);
    detailSheet.getRange(1, 1, 1, detailHeaders.length).setFontWeight('bold').setBackground('#1a365d').setFontColor('#ffffff');

    var detailRows = data.itemDetailRows.map(function(item) {
      var row = [item.category, item.item_name];
      staffNames.forEach(function(name) {
        row.push(item[name] ? '✅' : '⬜');
      });
      return row;
    });
    if (detailRows.length > 0) {
      detailSheet.getRange(2, 1, detailRows.length, detailHeaders.length).setValues(detailRows);
      // 가운데 정렬 (체크 부분)
      if (staffNames.length > 0) {
        detailSheet.getRange(2, 3, detailRows.length, staffNames.length).setHorizontalAlignment('center');
      }
    }

    detailSheet.autoResizeColumns(1, detailHeaders.length);

    return ContentService.createTextOutput(JSON.stringify({
      success: true,
      message: '동기화 완료',
      timestamp: new Date().toISOString()
    })).setMimeType(ContentService.MimeType.JSON);

  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({
      success: false,
      error: error.message
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

function getOrCreateSheet(ss, name) {
  var sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
  }
  return sheet;
}

// 테스트용 - Apps Script 에디터에서 실행하여 시트 구조 확인
function testSetup() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  getOrCreateSheet(ss, '전체 현황');
  getOrCreateSheet(ss, '품목별 상세');
  SpreadsheetApp.getUi().alert('시트가 준비되었습니다!');
}
