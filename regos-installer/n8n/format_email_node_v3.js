// ── RegOS Escalation: Format Email v3 ──
// Professional all-in-one HTML email template.
// Based on industry best practices from PagerDuty, Sentry, Linear.
//
// v3 changes:
//   - Table-based layout (Outlook-safe, no flexbox/grid/gradient)
//   - Proper chain-of-thought stripping from AI response
//   - Preheader text for inbox preview
//   - Single-column info cards (mobile-safe)
//   - Dark mode meta tags
//   - Truncation with character-safe cutoff (Gmail 102KB limit)
//   - Response sanitization (strips <details>, raw HTML entities)
//   - Inline CSS only (no <style> dependencies for layout)

const item = $input.first().json;

const caseRef = item.case_ref || 'UNKNOWN';
const trigger = (item.escalation?.trigger === 'manual') ? 'MANUAL' : 'AUTO';

// ── Confidence ──
const score = item.confidence?.score;
const band = item.confidence?.band;
let confidenceDisplay = '';
let confidencePct = null;
if (score != null && score > 0) {
  confidencePct = Math.round(score * 100);
  const bandLabel = band && band !== 'N/A' ? ` · ${band}` : '';
  confidenceDisplay = `${confidencePct}%${bandLabel}`;
} else {
  confidenceDisplay = 'N/A (non-RegOS response)';
}

// ── User info ──
const userName = item.user?.name || 'Unknown';
const userEmail = item.user?.email || '';
const userRole = item.user?.role || '';

// ── Reason ──
const reasonMap = {
  'manual_user_flag': 'Manually flagged by user',
  'low_confidence': 'Low confidence score',
  'threshold_breach': 'Confidence below threshold',
  'guardrail_triggered': 'Guardrail triggered',
};
const rawReason = item.escalation?.reason || 'Unknown';
const reason = reasonMap[rawReason] || rawReason.replace(/_/g, ' ');

const query = item.query || '(no query captured)';
const response = item.response || '(no response captured)';
const chatId = item.context?.chat_id || '';
const timestamp = item.timestamp || new Date().toISOString();

// ── Date formatting ──
const dateObj = new Date(timestamp);
const dateStr = dateObj.toLocaleString('en-US', {
  weekday: 'short', year: 'numeric', month: 'short', day: 'numeric',
  hour: '2-digit', minute: '2-digit', timeZoneName: 'short'
});

// ── Subject ──
const triggerLabel = trigger === 'MANUAL' ? 'Manual Flag' : 'Auto-Escalated';
const subject = `[RegOS Escalation] ${caseRef} — ${triggerLabel}`;

// ── User concern ──
const userConcern = item.escalation?.user_concern || '';

// ── Retrieval context ──
const citations = item.retrieval_context?.graphrag_citations || [];
const kbSources = item.retrieval_context?.kb_sources || [];
const entities = item.retrieval_context?.entity_matches || [];
const hasContext = citations.length > 0 || kbSources.length > 0;

// ═══════════════════════════════════════════════════════════════
// SANITIZATION — strips chain-of-thought, raw HTML, entities
// ═══════════════════════════════════════════════════════════════

function sanitizeResponse(text) {
  if (!text) return '';

  let clean = text;

  // 1. Strip <details>...</details> blocks (chain-of-thought reasoning)
  clean = clean.replace(/<details[^>]*>[\s\S]*?<\/details>/gi, '');

  // 2. Strip any remaining HTML tags that leaked through
  clean = clean.replace(/<\/?[a-z][a-z0-9]*\b[^>]*>/gi, '');

  // 3. Fix double-encoded HTML entities
  clean = clean.replace(/&amp;gt;/g, '>');
  clean = clean.replace(/&amp;lt;/g, '<');
  clean = clean.replace(/&amp;amp;/g, '&');
  clean = clean.replace(/&#x27;/g, "'");
  clean = clean.replace(/&gt;\s*/g, '');  // Remove stray > from blockquotes
  clean = clean.replace(/&lt;/g, '<');
  clean = clean.replace(/&amp;/g, '&');

  // 4. Clean up excessive whitespace left by stripping
  clean = clean.replace(/\n{3,}/g, '\n\n');
  clean = clean.trim();

  return clean;
}

// ═══════════════════════════════════════════════════════════════
// MARKDOWN → HTML (email-safe)
// ═══════════════════════════════════════════════════════════════

function md2html(text) {
  if (!text) return '';
  return text
    // Escape HTML first
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    // Headers
    .replace(/^### (.+)$/gm, '<strong style="display:block;color:#1B3A5C;margin:12px 0 4px;font-size:13px">$1</strong>')
    .replace(/^## (.+)$/gm, '<strong style="display:block;color:#1B3A5C;margin:14px 0 6px;font-size:14px">$1</strong>')
    .replace(/^# (.+)$/gm, '<strong style="display:block;color:#1B3A5C;margin:16px 0 8px;font-size:16px">$1</strong>')
    // Bold + italic
    .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code style="background:#F0F0F0;padding:1px 5px;border-radius:3px;font-size:12px;font-family:Menlo,Monaco,monospace">$1</code>')
    // Citations [G1], [G2]
    .replace(/\[(G\d+)\]/g, '<span style="background:#E8F4FD;color:#1B3A5C;padding:1px 5px;border-radius:3px;font-size:11px;font-weight:700">$1</span>')
    // Section references
    .replace(/(Sec(?:tion)?\.?\s*24[-–]\d+(?:\.\d+)*(?:\([^)]+\))?)/g, '<span style="background:#FFF3E0;padding:1px 5px;border-radius:3px;font-size:12px">$1</span>')
    // Unordered lists
    .replace(/^[-*] (.+)$/gm, '<div style="padding:2px 0 2px 16px;font-size:14px;line-height:1.5">&#8226; $1</div>')
    // Numbered lists
    .replace(/^(\d+)\. (.+)$/gm, '<div style="padding:2px 0 2px 16px;font-size:14px;line-height:1.5">$1. $2</div>')
    // Horizontal rules
    .replace(/^---+$/gm, '<hr style="border:none;border-top:1px solid #E0E0E0;margin:12px 0">')
    // Paragraphs
    .replace(/\n\n/g, '</p><p style="margin:8px 0;font-size:14px;line-height:1.6">')
    .replace(/\n/g, '<br>');
}

// ═══════════════════════════════════════════════════════════════
// PROCESS RESPONSE — sanitize then convert
// ═══════════════════════════════════════════════════════════════

const cleanResponse = sanitizeResponse(response);
const MAX_RESPONSE_CHARS = 2000;
const responseTruncated = cleanResponse.length > MAX_RESPONSE_CHARS;
const responseSnippet = responseTruncated
  ? cleanResponse.substring(0, MAX_RESPONSE_CHARS).replace(/\s+\S*$/, '') + '…'
  : cleanResponse;
const responseHtml = md2html(responseSnippet);

// ═══════════════════════════════════════════════════════════════
// COLORS & STYLING CONSTANTS
// ═══════════════════════════════════════════════════════════════

const BRAND = '#1B3A5C';
const BRAND_LIGHT = '#2C5F8A';
const ACCENT = '#1DA1D4';
const BG_PAGE = '#F4F6F8';
const BG_CARD = '#FFFFFF';
const BG_MUTED = '#F8F9FB';
const BORDER = '#E2E8F0';
const TEXT_PRIMARY = '#1A202C';
const TEXT_SECONDARY = '#4A5568';
const TEXT_MUTED = '#A0AEC0';

// Trigger badge
const triggerBg = trigger === 'MANUAL' ? '#DD6B20' : '#C53030';
const triggerBadge = trigger === 'MANUAL' ? 'MANUAL FLAG' : 'AUTO-ESCALATED';

// Confidence color
const confColor = confidencePct >= 85 ? '#38A169' : confidencePct >= 60 ? '#D69E2E' : confidencePct != null ? '#E53E3E' : TEXT_MUTED;

// ═══════════════════════════════════════════════════════════════
// BUILD CONTEXT SECTION
// ═══════════════════════════════════════════════════════════════

let contextRows = '';
if (citations.length > 0) {
  const citationList = citations.slice(0, 5).map((c, i) => {
    const section = c.section || c.id || `Citation ${i+1}`;
    return `<tr><td style="padding:6px 12px;font-size:12px;color:${TEXT_SECONDARY};border-bottom:1px solid ${BORDER}"><span style="background:#E8F4FD;color:${BRAND};padding:1px 5px;border-radius:3px;font-size:11px;font-weight:700">G${c.index || i+1}</span>&nbsp; ${section}</td></tr>`;
  }).join('');
  contextRows = `
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-top:8px">
      ${citationList}
    </table>`;
}

// ═══════════════════════════════════════════════════════════════
// PREHEADER — visible in inbox preview, hidden in email body
// ═══════════════════════════════════════════════════════════════

const preheaderText = `${triggerBadge}: ${caseRef} — ${reason}. ${userName} flagged a response for review.`;

// ═══════════════════════════════════════════════════════════════
// HTML EMAIL TEMPLATE
// ═══════════════════════════════════════════════════════════════

const htmlBody = `<!DOCTYPE html>
<html lang="en" xmlns:v="urn:schemas-microsoft-com:vml">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <meta name="supported-color-schemes" content="light dark">
  <title>${subject}</title>
  <!--[if mso]><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml><![endif]-->
</head>
<body style="margin:0;padding:0;background-color:${BG_PAGE};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased">

  <!-- Preheader (inbox preview text, hidden in body) -->
  <div style="display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;overflow:hidden;color:${BG_PAGE}">${preheaderText}&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;</div>

  <!-- Outer wrapper -->
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:${BG_PAGE}">
    <tr>
      <td align="center" style="padding:32px 16px">

        <!-- Main card: 600px -->
        <table width="600" cellpadding="0" cellspacing="0" border="0" style="background-color:${BG_CARD};border-radius:8px;border:1px solid ${BORDER}">

          <!-- ═══ HEADER ═══ -->
          <tr>
            <td style="background-color:${BRAND};padding:24px 32px;border-radius:8px 8px 0 0">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td>
                    <span style="font-size:20px;font-weight:700;color:#FFFFFF;letter-spacing:-0.3px">RegOS</span>
                    <span style="font-size:20px;font-weight:300;color:#A8C8E8;letter-spacing:-0.3px"> Escalation</span>
                  </td>
                  <td align="right" valign="top">
                    <table cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td style="background-color:${triggerBg};padding:5px 14px;border-radius:4px">
                          <span style="color:#FFFFFF;font-size:11px;font-weight:700;letter-spacing:0.8px;text-transform:uppercase">${triggerBadge}</span>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td colspan="2" style="padding-top:8px">
                    <span style="font-size:13px;color:#A8C8E8">${dateStr}</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- ═══ CASE SUMMARY BAR ═══ -->
          <tr>
            <td style="background-color:${BG_MUTED};padding:16px 32px;border-bottom:1px solid ${BORDER}">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td width="50%" valign="top" style="padding-right:16px">
                    <span style="font-size:10px;font-weight:600;color:${TEXT_MUTED};text-transform:uppercase;letter-spacing:1px">Case Reference</span><br>
                    <span style="font-size:16px;font-weight:700;color:${BRAND};font-family:Menlo,Monaco,'Courier New',monospace;letter-spacing:0.5px">${caseRef}</span>
                  </td>
                  <td width="50%" valign="top">
                    <span style="font-size:10px;font-weight:600;color:${TEXT_MUTED};text-transform:uppercase;letter-spacing:1px">Confidence</span><br>
                    <span style="font-size:16px;font-weight:700;color:${confColor}">${confidenceDisplay}</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- ═══ BODY CONTENT ═══ -->
          <tr>
            <td style="padding:28px 32px">

              <!-- Reason + Flagged By -->
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:24px">
                <tr>
                  <td style="padding-bottom:10px">
                    <span style="font-size:10px;font-weight:600;color:${TEXT_MUTED};text-transform:uppercase;letter-spacing:1px">Reason</span><br>
                    <span style="font-size:14px;color:${TEXT_PRIMARY}">${reason}</span>
                  </td>
                </tr>
                <tr>
                  <td>
                    <span style="font-size:10px;font-weight:600;color:${TEXT_MUTED};text-transform:uppercase;letter-spacing:1px">Flagged By</span><br>
                    <span style="font-size:14px;color:${TEXT_PRIMARY}">${userName}</span>${userEmail ? `<span style="font-size:13px;color:${TEXT_SECONDARY}"> &lt;${userEmail}&gt;</span>` : ''}${userRole ? ` <span style="display:inline-block;background:#EBF4FF;color:${BRAND};padding:1px 8px;border-radius:3px;font-size:11px;font-weight:600">${userRole}</span>` : ''}
                  </td>
                </tr>
              </table>

              <!-- ─── USER QUERY ─── -->
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:24px">
                <tr>
                  <td style="padding-bottom:10px">
                    <span style="font-size:13px;font-weight:700;color:${BRAND};text-transform:uppercase;letter-spacing:0.5px">User Query</span>
                  </td>
                </tr>
                <tr>
                  <td>
                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td width="4" style="background-color:${ACCENT}"></td>
                        <td style="background-color:#F7FAFC;padding:14px 16px;font-size:14px;line-height:1.6;color:${TEXT_PRIMARY}">${md2html(query)}</td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <!-- ─── AI RESPONSE ─── -->
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:24px">
                <tr>
                  <td style="padding-bottom:10px">
                    <span style="font-size:13px;font-weight:700;color:${BRAND};text-transform:uppercase;letter-spacing:0.5px">AI Response</span>
                    <span style="font-size:11px;font-weight:600;color:#DD6B20;margin-left:8px;background:#FFFBEB;padding:2px 8px;border-radius:3px">UNDER REVIEW</span>
                  </td>
                </tr>
                <tr>
                  <td>
                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td width="4" style="background-color:#DD6B20"></td>
                        <td style="background-color:#FFFCF5;padding:14px 16px;font-size:13px;line-height:1.7;color:${TEXT_SECONDARY}">
                          <p style="margin:0">${responseHtml}</p>
                          ${responseTruncated ? `<p style="margin:12px 0 0;font-size:12px;color:${TEXT_MUTED};font-style:italic">Response truncated for email. Full text attached as JSON.</p>` : ''}
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              ${userConcern.trim() ? `
              <!-- ─── REVIEWER NOTE ─── -->
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:24px">
                <tr>
                  <td style="padding-bottom:10px">
                    <span style="font-size:13px;font-weight:700;color:${BRAND};text-transform:uppercase;letter-spacing:0.5px">Reviewer Note</span>
                    <span style="font-size:11px;color:${TEXT_SECONDARY};margin-left:6px">from ${userName}</span>
                  </td>
                </tr>
                <tr>
                  <td>
                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td width="4" style="background-color:#E53E3E"></td>
                        <td style="background-color:#FFF5F5;padding:14px 16px;font-size:14px;line-height:1.6;color:${TEXT_PRIMARY}">${md2html(userConcern)}</td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
              ` : ''}

              ${contextRows ? `
              <!-- ─── RETRIEVAL CONTEXT ─── -->
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:24px">
                <tr>
                  <td style="padding-bottom:10px">
                    <span style="font-size:13px;font-weight:700;color:${BRAND};text-transform:uppercase;letter-spacing:0.5px">Retrieved Sections</span>
                    <span style="font-size:11px;color:${TEXT_MUTED};margin-left:6px">${citations.length} citation${citations.length !== 1 ? 's' : ''}</span>
                  </td>
                </tr>
                <tr>
                  <td style="background-color:${BG_MUTED};border-radius:4px;padding:8px 0">
                    ${contextRows}
                  </td>
                </tr>
              </table>
              ` : ''}


            </td>
          </tr>

          <!-- ═══ FOOTER ═══ -->
          <tr>
            <td style="background-color:${BG_MUTED};padding:20px 32px;border-top:1px solid ${BORDER};border-radius:0 0 8px 8px">
              ${chatId ? `<p style="margin:0 0 10px;font-size:11px;color:${TEXT_MUTED}"><strong style="color:${TEXT_SECONDARY}">Chat ID:</strong> <span style="font-family:Menlo,Monaco,'Courier New',monospace">${chatId}</span></p>` : ''}
              <p style="margin:0 0 6px;font-size:11px;color:${TEXT_MUTED};line-height:1.5">
                RegOS Escalation Pipeline v1.1.0&nbsp;&middot;&nbsp;Raw case file attached as JSON
              </p>
              <p style="margin:0;font-size:11px;color:${TEXT_MUTED};line-height:1.5">
                This is an automated notification&nbsp;&mdash;&nbsp;do not reply to this email.
              </p>
            </td>
          </tr>

        </table>
        <!-- /Main card -->

      </td>
    </tr>
  </table>
</body>
</html>`;

// ═══════════════════════════════════════════════════════════════
// PLAIN TEXT FALLBACK
// ═══════════════════════════════════════════════════════════════

const div = '━'.repeat(50);
const cleanForText = sanitizeResponse(response);
const textSnippet = cleanForText.length > 2000
  ? cleanForText.substring(0, 2000) + '\n… truncated — see attached JSON'
  : cleanForText;

const textBody = [
  `REGOS ESCALATION — ${caseRef}`,
  `${triggerBadge} | ${dateStr}`,
  div,
  '',
  `Case Reference:  ${caseRef}`,
  `Reason:          ${reason}`,
  `Confidence:      ${confidenceDisplay}`,
  `Flagged by:      ${userName}${userEmail ? ' <' + userEmail + '>' : ''}${userRole ? ' (' + userRole + ')' : ''}`,
  chatId ? `Chat ID:         ${chatId}` : '',
  '',
  div,
  'USER QUERY',
  div,
  query,
  '',
  div,
  'AI RESPONSE (UNDER REVIEW)',
  div,
  textSnippet,
  '',
  userConcern.trim() ? [div, `REVIEWER NOTE (from ${userName})`, div, userConcern, ''].join('\n') : '',
  div,
  'Raw case file attached as JSON.',
  '',
  'RegOS Escalation Pipeline v1.1.0',
  'This is an automated notification — do not reply.',
].filter(Boolean).join('\n');

return [{
  json: {
    ...item,
    email_subject: subject,
    email_html: htmlBody,
    email_text: textBody,
  },
  binary: $input.first().binary
}];
