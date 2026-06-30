function uploadForm(files, fieldName = 'files') {
  const formData = new FormData()
  files.forEach((file) => formData.append(fieldName, file))
  return formData
}

async function request(path, options = {}) {
  const response = await fetch(path, options)
  const data = await response.json().catch(() => ({}))

  if (!response.ok) {
    throw new Error(data.detail || data.message || `Request failed with status ${response.status}`)
  }

  return data
}

export async function loadFiles(files) {
  return request('/load', {
    method: 'POST',
    body: uploadForm(files)
  })
}

export async function loadSingleFile(file) {
  return request('/load-single', {
    method: 'POST',
    body: uploadForm([file], 'file')
  })
}

export async function pushUploadedFiles(files) {
  return request('/call-uploaded-files', {
    method: 'POST',
    body: uploadForm(files)
  })
}

export async function getUploadStatus() {
  return request('/status')
}

export async function clearUploadSession() {
  return request('/clear', { method: 'DELETE' })
}
