{{/*
Name
*/}}
{{- define "alert-webhook.name" -}}
alert-webhook
{{- end }}


{{/*
Full name
*/}}
{{- define "alert-webhook.fullname" -}}
{{- if contains "alert-webhook" .Release.Name }}
{{- .Release.Name }}
{{- else }}
{{- printf "%s-alert-webhook" .Release.Name }}
{{- end }}
{{- end }}