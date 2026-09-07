export function getFieldLabel(field) {
  const labels = {
    'roofline': 'Dachzeile',
    'headline': 'Titel',
    'subline': 'Untertitel',
    'teaser': 'Paywall-Teaser',
    'text': 'Text',
    'bulletpoints': 'Bulletpoints',
    'subheadings': 'Zwischenüberschriften',
    'tags': 'Tags',
    'shorten_text': 'Gekürzter Text'
  };
  return labels[field] || field;
}
