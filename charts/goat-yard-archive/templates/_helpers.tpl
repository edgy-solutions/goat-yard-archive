{{/*
Expand the name of the chart.
*/}}
{{- define "goat-yard-archive.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "goat-yard-archive.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "goat-yard-archive.chart" -}}
{{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "goat-yard-archive.labels" -}}
helm.sh/chart: {{ include "goat-yard-archive.chart" . }}
{{ include "goat-yard-archive.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "goat-yard-archive.selectorLabels" -}}
app.kubernetes.io/name: {{ include "goat-yard-archive.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Image reference for a first-party image.

Takes an `image` map. Emits `repository@<digest>` when `.digest` is set, and
`repository:<tag>` otherwise.

Why this exists: a tag can be re-pointed at a different artefact after the fact,
so a tag does not identify what was tested. A digest does. Anything that has been
smoked is deployed by digest; the tag path stays for the ordinary case.

Fails loudly rather than rendering a malformed image reference. `digest` wins over
`tag` when both are set, so a pin cannot be silently defeated by a leftover tag.
*/}}
{{- define "goat-yard-archive.image" -}}
{{- $repo := .repository | default "" -}}
{{- if not $repo -}}
{{- fail "image.repository is required" -}}
{{- end -}}
{{- $digest := .digest | default "" -}}
{{- if $digest -}}
{{- if not (hasPrefix "sha256:" $digest) -}}
{{- fail (printf "image.digest must be a full digest starting with \"sha256:\" (got %q)" $digest) -}}
{{- end -}}
{{- printf "%s@%s" $repo $digest -}}
{{- else -}}
{{- $tag := .tag | default "" -}}
{{- if not $tag -}}
{{- fail "image.tag is required when image.digest is not set" -}}
{{- end -}}
{{- printf "%s:%s" $repo $tag -}}
{{- end -}}
{{- end }}
