{{/*
Return the chart name.
*/}}
{{- define "shop.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Return the full release name.
*/}}
{{- define "shop.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name (include "shop.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Common labels for all resources.
*/}}
{{- define "shop.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: shop
{{- end }}

{{/*
Labels identifying one workload.
*/}}
{{- define "shop.workloadLabels" -}}
{{ include "shop.labels" . }}
app.kubernetes.io/name: {{ .workload }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Разнесение реплик: topologySpreadConstraints или podAntiAffinity.
Ожидает dict: root (.), workload (имя: api).
*/}}
{{- define "shop.spreading" -}}
{{- $root := .root -}}
{{- $workload := .workload -}}
{{- $s := $root.Values.spreading -}}
{{- if eq $s.mechanism "topologySpreadConstraints" }}
topologySpreadConstraints:
  - maxSkew: {{ $s.maxSkew }}
    topologyKey: {{ $s.topologyKey }}
    whenUnsatisfiable: {{ $s.whenUnsatisfiable }}
    labelSelector:
      matchLabels:
        app.kubernetes.io/name: {{ $workload }}
        app.kubernetes.io/instance: {{ $root.Release.Name }}
{{- else if eq $s.mechanism "podAntiAffinity" }}
affinity:
  podAntiAffinity:
{{- if eq $s.antiAffinityType "required" }}
    requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchLabels:
            app.kubernetes.io/name: {{ $workload }}
            app.kubernetes.io/instance: {{ $root.Release.Name }}
        topologyKey: {{ $s.topologyKey }}
{{- else }}
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchLabels:
              app.kubernetes.io/name: {{ $workload }}
              app.kubernetes.io/instance: {{ $root.Release.Name }}
          topologyKey: {{ $s.topologyKey }}
{{- end }}
{{- end }}
{{- end }}
