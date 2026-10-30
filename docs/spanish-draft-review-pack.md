# English / Mexican Spanish interface wording review pack

Status: accepted for synthetic-project interface use at the recorded snapshot.
See the [dated review record](evidence/spanish-interface-wording-2026-10-22.md).

This pack collects the source files named by LOC-001 draft markers and linked
requirements, including recovery, voice, care-team ownership/privacy, symptoms,
visits/cancellation, translation caveats, Profile and calendar labels. Entire
bilingual dictionaries are included conservatively where a marker covers only
part of a file. Inclusion does not revoke earlier accepted wording.

Dynamic rows show the exact source expression, including singular/plural and
conditional branches. Review both branches and preserve placeholders, names,
numbers, units, dates and safety/approval boundaries. They are not executable
instructions in this document. No patient-authored text or clinical record is included.

## Review method

1. Compare meaning, not word order: uncertainty, negation, timing and who may act.
2. Check no diagnosis, approval, delivery or continuous-monitoring claim is added.
3. Retain text fallback, confirmation before sharing, and emergency wording.
4. Record each decision by file/key with accepted text or a proposed correction.
5. Edit source copy and regenerate the pack after corrections; do not approve by
   deleting a draft comment alone. Clinical plan text still uses in-app bilingual approval.

A documented demo meaning-and-safety review is sufficient for this project;
a separate fluent reviewer is not required. Acceptance is limited to the exact
paired interface copy; it is not professional translation or clinical validation.
The receipt becomes invalid if the reviewed sources or pairs change. Regenerating
this pack alone never renews acceptance. Clinician-only English title/description
tuples are excluded; they are not translations.

## Source snapshot

Regenerate with `python backend/scripts/build_spanish_review_pack.py`;
check freshness with `python backend/scripts/build_spanish_review_pack.py --check --require-reviewed`.
Install the clinician portal's locked dependencies first for the TypeScript parser.

| Source | SHA-256 |
| --- | --- |
| [apps/patient-portal/src/content/chat-copy.ts](../apps/patient-portal/src/content/chat-copy.ts) | `68a36cfc9b2fd6a4724fb0f60b3f29ae0f66d83bc367d332363db6192af39d9a` |
| [apps/patient-portal/src/content/care-team-copy.ts](../apps/patient-portal/src/content/care-team-copy.ts) | `043b9a1eb79c7803a2f2e581463ac018fbf5917a34dc15713cdc6d8247eaedd9` |
| [apps/patient-portal/src/content/symptom-history-copy.ts](../apps/patient-portal/src/content/symptom-history-copy.ts) | `ba6a78638dd125919467d021b4a3cc35168937b84dee74c4c523353309a4f02e` |
| [apps/patient-portal/src/content/visits-copy.ts](../apps/patient-portal/src/content/visits-copy.ts) | `f757d83730909d6a74f3ec372db59a018d9c522e7b351680042f53e4e3efca41` |
| [apps/patient-portal/src/content/symptom-intake-copy.ts](../apps/patient-portal/src/content/symptom-intake-copy.ts) | `33d153f8b24540b8b1a32b926188aa840fabe420ee5de81b2de9f2b52c92edc8` |
| [apps/patient-portal/src/content/medication-confirmation-copy.ts](../apps/patient-portal/src/content/medication-confirmation-copy.ts) | `eeea959753c65c6c5efdec12daf9eb2a72070fce236c42deebbdb40138c8756c` |
| [apps/patient-portal/src/content/reply-sources-copy.ts](../apps/patient-portal/src/content/reply-sources-copy.ts) | `4c51318bbb6d181aa343bf8f496feedacb58032f5870fce18179d6fb2a824fda` |
| [apps/patient-portal/src/app/(app)/profile/profile-copy.ts](../apps/patient-portal/src/app/%28app%29/profile/profile-copy.ts) | `a8df7495058e93e633c6adb8f75bc7958c7226dbe72820d7734f70ba1a0e2bcc` |
| [apps/patient-portal/src/components/features/nora-conversations.tsx](../apps/patient-portal/src/components/features/nora-conversations.tsx) | `017df3a9f82e7ff9eaf1910f08129969133aba6e8cd7e0f03a85558f14a9d3c9` |
| [packages/shared/src/utils/care-conversations.ts](../packages/shared/src/utils/care-conversations.ts) | `283f87a82d5ba91f6e0430b1a9a37e25f874197105661317a8089f798b6010b5` |
| [backend/src/app/services/notification_centre_presentation.py](../backend/src/app/services/notification_centre_presentation.py) | `41387d20c93bc080df0e7bcfd048e9818c74782678c9533778d917c3ed3f89bd` |
| [backend/src/app/services/symptom_report_presenter.py](../backend/src/app/services/symptom_report_presenter.py) | `4cad3069d39cb12c334daa698b27b18bcc489fb0241b3934a7e7a98b123b8711` |
| [backend/src/app/services/appointment_calendar.py](../backend/src/app/services/appointment_calendar.py) | `321826d7839e1e15f867e02cebfc8555c71a95cf9ff030825f5ea4d7ed7bb569` |
| [backend/src/app/services/email_service.py](../backend/src/app/services/email_service.py) | `8ff3f52ed394057bfb4e9121b2fb65523939ec5cc5a18de97b0770a049b328bb` |

## Review list (650 paired rows)

Every listed pair is covered by the matching project-scope review receipt.
Use the source key to identify duplicate declaration/accessor entries
across screens; do not infer that similar strings have the same clinical context.

| Source/key | English (US) | Español (México) |
| --- | --- | --- |
| apps/patient-portal/src/content/chat-copy.ts:83 / `PATIENT_CHAT_COPY.safetySaveUncertain` | We could not verify that your message or care-team alert was saved. | No pudimos verificar que se guardara tu mensaje o la alerta para tu equipo clínico. |
| apps/patient-portal/src/content/chat-copy.ts:84 / `PATIENT_CHAT_COPY.safetyAlertPending` | The care-team alert is pending delivery. | La alerta para tu equipo clínico está pendiente de entrega. |
| apps/patient-portal/src/content/chat-copy.ts:85 / `PATIENT_CHAT_COPY.safetyAlertNoRecipients` | No care-team alert was saved because no linked recipient was available. | No se guardó una alerta para tu equipo clínico porque no había un destinatario vinculado disponible. |
| apps/patient-portal/src/content/chat-copy.ts:86 / `PATIENT_CHAT_COPY.careTeamLabel` | Care team messages | Mensajes del equipo clínico |
| apps/patient-portal/src/content/chat-copy.ts:87 / `PATIENT_CHAT_COPY.careTeamIntro` | Choose a linked clinician to exchange messages, separate from your AI conversation. | Elige a un profesional clínico vinculado para intercambiar mensajes, separados de tu conversación con IA. |
| apps/patient-portal/src/content/chat-copy.ts:88 / `PATIENT_CHAT_COPY.careTeamEmpty` | No care-team messages yet. | Todavía no hay mensajes de tu equipo clínico. |
| apps/patient-portal/src/content/chat-copy.ts:89 / `PATIENT_CHAT_COPY.historicalCareTeamLabel` | Historical care-team messages | Mensajes históricos del equipo clínico |
| apps/patient-portal/src/content/chat-copy.ts:90 / `PATIENT_CHAT_COPY.historicalCareTeamIntro` | Read-only prior messages. Sender and recipient routing is not available for these records. They are separate from addressed conversations and cannot be replied to here. | Mensajes anteriores de solo lectura. Estos registros no incluyen información sobre quién envió o recibió el mensaje. Están separados de las conversaciones dirigidas y no se pueden responder aquí. |
| apps/patient-portal/src/content/chat-copy.ts:91 / `PATIENT_CHAT_COPY.assistantDescription` | AI care assistant | Asistente de cuidado con IA |
| apps/patient-portal/src/content/chat-copy.ts:92 / `PATIENT_CHAT_COPY.typingMessage` | `${CARE_ASSISTANT_NAME} is typing...` | `${CARE_ASSISTANT_NAME} está escribiendo...` |
| apps/patient-portal/src/content/chat-copy.ts:93 / `PATIENT_CHAT_COPY.documentContextIntro` | Asking in | Consultando en |
| apps/patient-portal/src/content/chat-copy.ts:94 / `PATIENT_CHAT_COPY.documentContextSuffix` | . | . |
| apps/patient-portal/src/content/chat-copy.ts:96 / `PATIENT_CHAT_COPY.emptyStateIntro` | I can help with symptoms, results, and next steps. Try one of these prompts: | Puedo ayudarte con síntomas, resultados y próximos pasos. Prueba una de estas preguntas: |
| apps/patient-portal/src/content/chat-copy.ts:98 / `PATIENT_CHAT_COPY.escalationNotice` | Urgent symptoms detected. Contact your care team today. If symptoms are severe, seek emergency care now. | Se detectaron síntomas urgentes. Contacta a tu equipo clínico hoy. Si los síntomas son graves, busca atención de emergencia ahora. |
| apps/patient-portal/src/content/chat-copy.ts:99 / `PATIENT_CHAT_COPY.inputPlaceholder` | Type or speak a message... | Escribe o habla un mensaje... |
| apps/patient-portal/src/content/chat-copy.ts:100 / `PATIENT_CHAT_COPY.quickPrompts` | [ "Explain my recent results", "Should I worry about this symptom?", "Help me prepare questions for my doctor", ] | [ "Explica mis resultados recientes", "¿Debo preocuparme por este síntoma?", "Ayúdame a preparar preguntas para mi médico", ] |
| apps/patient-portal/src/content/chat-copy.ts:106 / `PATIENT_CHAT_COPY.welcomeMessage` | Hi. I can help explain results, track symptoms, and prepare questions for your doctor. | Hola. Puedo ayudarte a entender resultados, seguir síntomas y preparar preguntas para tu médico. |
| apps/patient-portal/src/content/chat-copy.ts:117 / `getChatRecoveryCopy.interrupted` | The reply was interrupted | La respuesta quedó incompleta |
| apps/patient-portal/src/content/chat-copy.ts:118 / `getChatRecoveryCopy.uncertain` | An action may already have been recorded. We will not repeat it automatically. Contact your care team if you need help. | Es posible que se haya registrado una acción. No la repetiremos automáticamente. Si necesitas ayuda, contacta a tu equipo de atención. |
| apps/patient-portal/src/content/chat-copy.ts:120 / `getChatRecoveryCopy.leaveAndReturn` | You can leave; the reply will appear here. | Puedes salir; la respuesta aparecerá aquí. |
| apps/patient-portal/src/content/chat-copy.ts:121 / `getChatRecoveryCopy.safeRetry` | You can retry the same message without sending it twice. | Puedes reintentar el mismo mensaje sin enviarlo dos veces. |
| apps/patient-portal/src/content/chat-copy.ts:122 / `getChatRecoveryCopy.noRetry` | We will not rerun this message. You can continue with a new question. | No volveremos a procesar este mensaje. Puedes continuar con una pregunta nueva. |
| apps/patient-portal/src/content/chat-copy.ts:123 / `getChatRecoveryCopy.retry` | Retry message | Reintentar mensaje |
| apps/patient-portal/src/content/chat-copy.ts:124 / `getChatRecoveryCopy.leaveUnfinished` | Leave this reply unfinished | Dejar esta respuesta incompleta |
| apps/patient-portal/src/content/chat-copy.ts:125 / `getChatRecoveryCopy.reconnectBeforeRetry` | Reconnect chat before retrying this message. | Vuelve a conectar el chat para reintentar este mensaje. |
| apps/patient-portal/src/content/chat-copy.ts:126 / `getChatRecoveryCopy.waitBeforeRetry` | Wait for the reply in progress to finish before retrying this message. | Espera a que termine la respuesta en curso antes de reintentar este mensaje. |
| apps/patient-portal/src/content/chat-copy.ts:127 / `getChatRecoveryCopy.busy` | A reply is already in progress in this conversation, possibly in another tab. We are recovering it. Your new message is still in the composer. | Ya hay una respuesta en curso en esta conversación, posiblemente en otra pestaña. Estamos recuperándola. Tu nuevo mensaje sigue en el cuadro de texto. |
| apps/patient-portal/src/content/chat-copy.ts:128 / `getChatRecoveryCopy.expired` | That reply took too long and was not kept. Your message is saved: use Retry message below. | Esa respuesta tardó demasiado y no se guardó. Tu mensaje está guardado: usa Reintentar mensaje más abajo. |
| apps/patient-portal/src/content/chat-copy.ts:129 / `getChatRecoveryCopy.unavailable` | Nora is temporarily unavailable. No message will be sent until chat reconnects. You can retry the connection. | Nora no está disponible en este momento. No se enviará ningún mensaje hasta que el chat vuelva a conectarse. Puedes reintentar la conexión. |
| apps/patient-portal/src/content/chat-copy.ts:130 / `getChatRecoveryCopy.reconnect` | Reconnect chat | Volver a conectar |
| apps/patient-portal/src/content/chat-copy.ts:131 / `getChatRecoveryCopy.replyUnavailable` | The reply for this message is no longer available. We will not rerun it. You can continue with a new question. | La respuesta a este mensaje ya no está disponible. No volveremos a procesarlo. Puedes continuar con una pregunta nueva. |
| apps/patient-portal/src/content/chat-copy.ts:152 / `getChatControlsCopy.connection.idle` | Offline | Sin conexión |
| apps/patient-portal/src/content/chat-copy.ts:152 / `getChatControlsCopy.connection.connected` | Connected | Conectado |
| apps/patient-portal/src/content/chat-copy.ts:152 / `getChatControlsCopy.connection.connecting` | Connecting… | Conectando… |
| apps/patient-portal/src/content/chat-copy.ts:152 / `getChatControlsCopy.connection.disconnected` | Offline | Sin conexión |
| apps/patient-portal/src/content/chat-copy.ts:152 / `getChatControlsCopy.connection.error` | Connection issue | Problema de conexión |
| apps/patient-portal/src/content/chat-copy.ts:152 / `getChatControlsCopy.connection.reconnecting` | Reconnecting… | Reconectando… |
| apps/patient-portal/src/content/chat-copy.ts:153 / `getChatControlsCopy.caution` | Nora is AI and can make mistakes. Check with your care team before changing treatment. For an emergency, call 911. | Nora es una IA y puede equivocarse. No cambies tu tratamiento sin consultar a tu equipo clínico. Para una emergencia, llama al 911. |
| apps/patient-portal/src/content/chat-copy.ts:154 / `getChatControlsCopy.loading` | Loading conversation… | Cargando conversación… |
| apps/patient-portal/src/content/chat-copy.ts:154 / `getChatControlsCopy.recordContext` | Record context attached | Registro adjunto |
| apps/patient-portal/src/content/chat-copy.ts:154 / `getChatControlsCopy.dismiss` | Dismiss | Cerrar |
| apps/patient-portal/src/content/chat-copy.ts:154 / `getChatControlsCopy.message` | Message to Nora | Mensaje para Nora |
| apps/patient-portal/src/content/chat-copy.ts:154 / `getChatControlsCopy.send` | Send message | Enviar mensaje |
| apps/patient-portal/src/content/chat-copy.ts:155 / `getChatControlsCopy.documentUnavailable` | This document is unavailable or has changed. Dismiss it before asking about the rest of your record. | Este documento no está disponible o cambió. Desvincúlalo antes de hacer una pregunta sobre el resto de tu expediente. |
| apps/patient-portal/src/content/chat-copy.ts:156 / `getChatControlsCopy.speak` | Tap to speak | Toca para hablar |
| apps/patient-portal/src/content/chat-copy.ts:156 / `getChatControlsCopy.stopVoice` | Stop voice recording | Detener grabación de voz |
| apps/patient-portal/src/content/chat-copy.ts:156 / `getChatControlsCopy.interrupt` | Interrupt and speak | Interrumpir y hablar |
| apps/patient-portal/src/content/chat-copy.ts:156 / `getChatControlsCopy.listening` | Listening… | Escuchando… |
| apps/patient-portal/src/content/chat-copy.ts:156 / `getChatControlsCopy.transcribing` | Transcribing… | Transcribiendo… |
| apps/patient-portal/src/content/chat-copy.ts:157 / `getChatControlsCopy.handsFreeOn` | Hands-free mode is on. Tap to turn off. | Manos libres activado. Toca para desactivarlo. |
| apps/patient-portal/src/content/chat-copy.ts:157 / `getChatControlsCopy.handsFreeOff` | Turn on hands-free mode | Activar manos libres |
| apps/patient-portal/src/content/chat-copy.ts:157 / `getChatControlsCopy.autoPlay` | Voice replies will play automatically. | Las respuestas de voz se reproducirán automáticamente. |
| apps/patient-portal/src/content/chat-copy.ts:158 / `getChatControlsCopy.chatError` | Could not load or complete the conversation. Check your connection and try again. | No se pudo cargar o completar la conversación. Revisa la conexión y vuelve a intentarlo. |
| apps/patient-portal/src/content/chat-copy.ts:158 / `getChatControlsCopy.voiceError` | Could not complete the voice action. You can type your message. | No se pudo completar la función de voz. Puedes escribir tu mensaje. |
| apps/patient-portal/src/content/chat-copy.ts:159 / `getChatControlsCopy.original` | Original language | Idioma original |
| apps/patient-portal/src/content/chat-copy.ts:159 / `getChatControlsCopy.originalUnknown` | Original message · language not recorded | Mensaje original · idioma no registrado |
| apps/patient-portal/src/content/chat-copy.ts:159 / `getChatControlsCopy.live` | Live response | Respuesta en curso |
| apps/patient-portal/src/content/chat-copy.ts:159 / `getChatControlsCopy.listen` | Listen | Escuchar |
| apps/patient-portal/src/content/chat-copy.ts:160 / `getChatControlsCopy.humanOriginal` | Messages appear as written, without automatic translation. | Los mensajes se muestran tal como se escribieron, sin traducción automática. |
| apps/patient-portal/src/content/chat-copy.ts:162 / `getChatControlsCopy.sending` | Sending… | Enviando… |
| apps/patient-portal/src/content/chat-copy.ts:162 / `getChatControlsCopy.notSent` | Not sent | No se envió |
| apps/patient-portal/src/content/chat-copy.ts:162 / `getChatControlsCopy.retrySend` | Retry | Reintentar |
| apps/patient-portal/src/content/chat-copy.ts:162 / `getChatControlsCopy.removeUnsent` | Remove | Quitar |
| apps/patient-portal/src/content/chat-copy.ts:163 / `getChatControlsCopy.profileRequired` | Your preferred language needs to load before sending. If this takes too long, reopen Chat. | Necesitamos cargar tu idioma preferido antes de enviar. Si tarda demasiado, vuelve a abrir Chat. |
| apps/patient-portal/src/content/chat-copy.ts:182 / `getChatResultsCopy.eyebrow` | Results from this report | Resultados de este reporte |
| apps/patient-portal/src/content/chat-copy.ts:183 / `getChatResultsCopy.fallbackTitle` | Your report | Tu reporte |
| apps/patient-portal/src/content/chat-copy.ts:184 / `getChatResultsCopy.criticalContact` | Contact your care team today. | Comunícate hoy con tu equipo de atención. |
| apps/patient-portal/src/content/chat-copy.ts:185 / `getChatResultsCopy.criticalEmergency` | Call 911 if you have chest pain, palpitations or trouble breathing. | Llama al 911 si tienes dolor de pecho, palpitaciones o dificultad para respirar. |
| apps/patient-portal/src/content/chat-copy.ts:186 / `getChatResultsCopy.outOfRange` | Outside the report's range | Fuera del rango del reporte |
| apps/patient-portal/src/content/chat-copy.ts:187 / `getChatResultsCopy.allWithinRange` | All results are within the report's ranges. | Todos los resultados están dentro de los rangos del reporte. |
| apps/patient-portal/src/content/chat-copy.ts:188 / `getChatResultsCopy.showInRange` | (count: number) =&gt; count === 1 ? "Show 1 result in range" : `Show ${count} results in range` | (count: number) =&gt; count === 1 ? "Mostrar 1 resultado dentro del rango" : `Mostrar ${count} resultados dentro del rango` |
| apps/patient-portal/src/content/chat-copy.ts:189 / `getChatResultsCopy.hideInRange` | Hide results in range | Ocultar resultados dentro del rango |
| apps/patient-portal/src/content/chat-copy.ts:190 / `getChatResultsCopy.showMeasurements` | (count: number) =&gt; count === 1 ? "Show 1 measurement" : `Show ${count} measurements` | (count: number) =&gt; count === 1 ? "Mostrar 1 medición" : `Mostrar ${count} mediciones` |
| apps/patient-portal/src/content/chat-copy.ts:191 / `getChatResultsCopy.hideMeasurements` | Hide measurements | Ocultar mediciones |
| apps/patient-portal/src/content/chat-copy.ts:192 / `getChatResultsCopy.inRange` | In range | Dentro del rango |
| apps/patient-portal/src/content/chat-copy.ts:193 / `getChatResultsCopy.measurements` | Measurements | Mediciones |
| apps/patient-portal/src/content/chat-copy.ts:194 / `getChatResultsCopy.notReviewed` | Read automatically · not yet reviewed by your care team | Leído automáticamente · aún no revisado por tu equipo de atención |
| apps/patient-portal/src/content/chat-copy.ts:195 / `getChatResultsCopy.reviewed` | Reviewed by your care team | Revisado por tu equipo de atención |
| apps/patient-portal/src/content/chat-copy.ts:196 / `getChatResultsCopy.seeInRecords` | See in Records | Ver en Registros |
| apps/patient-portal/src/content/chat-copy.ts:224 / `getVoiceModeCopy.start` | Voice conversation | Conversación por voz |
| apps/patient-portal/src/content/chat-copy.ts:225 / `getVoiceModeCopy.panel` | Voice conversation with Nora | Conversación por voz con Nora |
| apps/patient-portal/src/content/chat-copy.ts:227 / `getVoiceModeCopy.status.connecting` | Connecting voice… | Conectando la voz… |
| apps/patient-portal/src/content/chat-copy.ts:228 / `getVoiceModeCopy.status.listening` | Listening. Speak whenever you are ready. | Te escucho. Habla cuando quieras. |
| apps/patient-portal/src/content/chat-copy.ts:229 / `getVoiceModeCopy.status.hearing` | Hearing you… | Te estoy escuchando… |
| apps/patient-portal/src/content/chat-copy.ts:230 / `getVoiceModeCopy.status.thinking` | Nora is thinking | Nora está pensando |
| apps/patient-portal/src/content/chat-copy.ts:231 / `getVoiceModeCopy.status.speaking` | Nora is speaking. Talk to interrupt. | Nora está hablando. Habla para interrumpir. |
| apps/patient-portal/src/content/chat-copy.ts:232 / `getVoiceModeCopy.status.paused` | Microphone paused | Micrófono en pausa |
| apps/patient-portal/src/content/chat-copy.ts:234 / `getVoiceModeCopy.pause` | Pause | Pausar |
| apps/patient-portal/src/content/chat-copy.ts:235 / `getVoiceModeCopy.resume` | Resume | Reanudar |
| apps/patient-portal/src/content/chat-copy.ts:236 / `getVoiceModeCopy.end` | End voice mode | Terminar modo de voz |
| apps/patient-portal/src/content/chat-copy.ts:237 / `getVoiceModeCopy.remaining` | (minutes: number, seconds: number) =&gt; `${minutes}:${String(seconds).padStart(2, "0")} left in this voice session` | (minutes: number, seconds: number) =&gt; `Quedan ${minutes}:${String(seconds).padStart(2, "0")} en esta sesión de voz` |
| apps/patient-portal/src/content/chat-copy.ts:238 / `getVoiceModeCopy.heard` | What you are saying | Lo que dices |
| apps/patient-portal/src/content/chat-copy.ts:240 / `getVoiceModeCopy.errors.permission_denied` | Microphone access is blocked. Allow it in your browser settings, or use text instead. | El acceso al micrófono está bloqueado. Permítelo en la configuración del navegador o usa texto. |
| apps/patient-portal/src/content/chat-copy.ts:241 / `getVoiceModeCopy.errors.no_microphone` | No microphone was found. Connect one, or use text instead. | No encontramos un micrófono. Conecta uno o usa texto. |
| apps/patient-portal/src/content/chat-copy.ts:242 / `getVoiceModeCopy.errors.unsupported` | This browser cannot do voice conversations. You can use text instead. | Este navegador no permite la conversación por voz. Puedes usar texto. |
| apps/patient-portal/src/content/chat-copy.ts:243 / `getVoiceModeCopy.errors.provider_unavailable` | Voice is not available right now. You can keep going by text. | La voz no está disponible en este momento. Puedes seguir por texto. |
| apps/patient-portal/src/content/chat-copy.ts:244 / `getVoiceModeCopy.errors.network` | The voice connection was lost. Check your connection, or use text instead. | Se perdió la conexión de voz. Revisa tu conexión o usa texto. |
| apps/patient-portal/src/content/chat-copy.ts:245 / `getVoiceModeCopy.errors.session_limit` | This voice session reached its time limit. You can start another or use text. | La sesión de voz llegó a su límite de tiempo. Puedes iniciar otra o usar texto. |
| apps/patient-portal/src/content/chat-copy.ts:246 / `getVoiceModeCopy.errors.idle_timeout` | Voice mode closed because nothing was heard for a while. Start it again or use text. | Cerramos la voz porque no se oyó nada por un rato. Puedes iniciarla de nuevo o usar texto. |
| apps/patient-portal/src/content/chat-copy.ts:247 / `getVoiceModeCopy.errors.failed` | Voice could not start. Try again, or use text instead. | No se pudo iniciar la voz. Inténtalo de nuevo o usa texto. |
| apps/patient-portal/src/content/chat-copy.ts:250 / `getVoiceModeCopy.notices.speech_unavailable` | Nora's reply is in the chat. Audio is not available right now. | La respuesta de Nora está en el chat. El audio no está disponible ahora. |
| apps/patient-portal/src/content/chat-copy.ts:251 / `getVoiceModeCopy.notices.not_sent` | That message could not be sent. It is in the message box so you can send it. | No se pudo enviar ese mensaje. Quedó en el cuadro de mensaje para que lo envíes. |
| apps/patient-portal/src/content/chat-copy.ts:252 / `getVoiceModeCopy.notices.reply_failed` | Nora could not answer that. Your message is saved in the chat. | Nora no pudo responder a eso. Tu mensaje quedó guardado en el chat. |
| apps/patient-portal/src/content/chat-copy.ts:254 / `getVoiceModeCopy.tryAgain` | Try again | Intentar de nuevo |
| apps/patient-portal/src/content/chat-copy.ts:255 / `getVoiceModeCopy.useText` | Use text instead | Usar texto |
| apps/patient-portal/src/content/care-team-copy.ts:65 / `copy.and` | and | y |
| apps/patient-portal/src/content/care-team-copy.ts:66 / `copy.filterLabel` | Filter by care team | Filtrar por equipo de atención |
| apps/patient-portal/src/content/care-team-copy.ts:67 / `copy.filterAll` | All | Todas |
| apps/patient-portal/src/content/care-team-copy.ts:68 / `copy.filterUnowned` | No longer on your care team | Ya no está en tu equipo de atención |
| apps/patient-portal/src/content/care-team-copy.ts:69 / `copy.filterEmpty` | Nothing for this care team today. | No hay nada de este equipo de atención hoy. |
| apps/patient-portal/src/content/care-team-copy.ts:70 / `copy.filterEmptyAction` | Show all | Mostrar todas |
| apps/patient-portal/src/content/care-team-copy.ts:71 / `copy.unownedNotice` | (name: string &#124; null) =&gt; name ? `Prescribed by ${name}, no longer on your care team. Ask your care team before changing it.` : "Prescribed by a clinician who is no longer on your care team. Ask your care team before changing it." | (name) =&gt; name ? `Recetado por ${name}, que ya no está en tu equipo de atención. Consulta con tu equipo de atención antes de cambiarlo.` : "Recetado por un clínico que ya no está en tu equipo de atención. Consulta con tu equipo de atención antes de cambiarlo." |
| apps/patient-portal/src/content/care-team-copy.ts:75 / `copy.contactClinicTitle` | Contact your clinic | Comunícate con tu clínica |
| apps/patient-portal/src/content/care-team-copy.ts:77 / `copy.contactClinicBody` | Some of your activities were prescribed by a clinician who is no longer on your care team, and you have no active care team right now. Please contact your clinic before changing any of them. Your reminders continue. | Algunas de tus actividades fueron recetadas por un clínico que ya no está en tu equipo de atención, y ahora no tienes un equipo de atención activo. Comunícate con tu clínica antes de cambiar cualquiera de ellas. Tus recordatorios continúan. |
| apps/patient-portal/src/content/care-team-copy.ts:78 / `copy.planGroupLabel` | (owner: string) =&gt; `Care plan from ${owner}` | (owner) =&gt; `Plan de atención de ${owner}` |
| apps/patient-portal/src/content/care-team-copy.ts:79 / `copy.planGroupVersion` | (version: number, date: string &#124; null) =&gt; (date ? `Version ${version} · approved ${date}` : `Version ${version}`) | (version, date) =&gt; (date ? `Versión ${version} · aprobado el ${date}` : `Versión ${version}`) |
| apps/patient-portal/src/content/care-team-copy.ts:80 / `copy.uploadTitle` | Which care team is this for? | ¿Para qué equipo de atención es esto? |
| apps/patient-portal/src/content/care-team-copy.ts:81 / `copy.uploadHelp` | The care team you choose will review this document. | El equipo de atención que elijas revisará este documento. |
| apps/patient-portal/src/content/care-team-copy.ts:82 / `copy.uploadFile` | (name: string) =&gt; `File: ${name}` | (name) =&gt; `Archivo: ${name}` |
| apps/patient-portal/src/content/care-team-copy.ts:83 / `copy.uploadNotSure` | Not sure | No estoy seguro |
| apps/patient-portal/src/content/care-team-copy.ts:84 / `copy.uploadNotSureHint` | Your care teams will decide who reviews it. | Tus equipos de atención decidirán quién lo revisa. |
| apps/patient-portal/src/content/care-team-copy.ts:85 / `copy.uploadSingleHint` | This document will go to your care team below. | Este documento irá a tu equipo de atención que aparece abajo. |
| apps/patient-portal/src/content/care-team-copy.ts:86 / `copy.uploadRequired` | Choose a care team, or “Not sure”, to continue. | Elige un equipo de atención, o “No estoy seguro”, para continuar. |
| apps/patient-portal/src/content/care-team-copy.ts:87 / `copy.uploadConfirm` | Upload document | Subir documento |
| apps/patient-portal/src/content/care-team-copy.ts:88 / `copy.uploadCancel` | Cancel | Cancelar |
| apps/patient-portal/src/content/care-team-copy.ts:89 / `copy.uploadLoading` | Checking your care teams… | Revisando tus equipos de atención… |
| apps/patient-portal/src/content/care-team-copy.ts:90 / `copy.uploadOptionsError` | We could not load your care teams. Try again. | No pudimos cargar tus equipos de atención. Intenta de nuevo. |
| apps/patient-portal/src/content/care-team-copy.ts:91 / `copy.uploadRetry` | Try again | Intentar de nuevo |
| apps/patient-portal/src/content/care-team-copy.ts:92 / `copy.conditionsTitle` | Health conditions | Condiciones de salud |
| apps/patient-portal/src/content/care-team-copy.ts:93 / `copy.conditionsIntro` | Only the care team that recorded a private condition sees it. Medications and allergies are always shared for your safety. | Solo el equipo de atención que registró una condición privada la ve. Los medicamentos y las alergias siempre se comparten por tu seguridad. |
| apps/patient-portal/src/content/care-team-copy.ts:94 / `copy.conditionsLoadError` | Your health conditions could not be loaded. | No se pudieron cargar tus condiciones de salud. |
| apps/patient-portal/src/content/care-team-copy.ts:95 / `copy.conditionsRetry` | Try again | Intentar de nuevo |
| apps/patient-portal/src/content/care-team-copy.ts:96 / `copy.keepPrivate` | Keep private | Mantener privada |
| apps/patient-portal/src/content/care-team-copy.ts:97 / `copy.keepPrivateFor` | (name: string) =&gt; `Keep ${name} private` | (name) =&gt; `Mantener privada: ${name}` |
| apps/patient-portal/src/content/care-team-copy.ts:98 / `copy.keepPrivateHelp` | Only the care team that recorded this sees it. Medications and allergies are always shared for your safety. | Solo el equipo de atención que la registró la ve. Los medicamentos y las alergias siempre se comparten por tu seguridad. |
| apps/patient-portal/src/content/care-team-copy.ts:99 / `copy.recordedBy` | (owner: string) =&gt; `Recorded by ${owner}` | (owner) =&gt; `Registrada por ${owner}` |
| apps/patient-portal/src/content/care-team-copy.ts:100 / `copy.privateConfirmTitle` | Keep this condition private? | ¿Mantener esta condición privada? |
| apps/patient-portal/src/content/care-team-copy.ts:101 / `copy.privateConfirmBody` | Only the care team that recorded it will see it. Your other care teams will see that some conditions are kept private, but not which ones. | Solo el equipo de atención que la registró la verá. Tus otros equipos de atención verán que algunas condiciones se mantienen privadas, pero no cuáles. |
| apps/patient-portal/src/content/care-team-copy.ts:102 / `copy.sharedConfirmTitle` | Share this condition again? | ¿Volver a compartir esta condición? |
| apps/patient-portal/src/content/care-team-copy.ts:103 / `copy.sharedConfirmBody` | Your other care teams will be able to see it. Medications and allergies are always shared for your safety. | Tus otros equipos de atención podrán verla. Los medicamentos y las alergias siempre se comparten por tu seguridad. |
| apps/patient-portal/src/content/care-team-copy.ts:104 / `copy.confirm` | Confirm | Confirmar |
| apps/patient-portal/src/content/care-team-copy.ts:105 / `copy.cancel` | Cancel | Cancelar |
| apps/patient-portal/src/content/care-team-copy.ts:106 / `copy.saving` | Saving… | Guardando… |
| apps/patient-portal/src/content/care-team-copy.ts:107 / `copy.privacySaved` | (name: string, privateNow: boolean) =&gt; (privateNow ? `${name} is now private.` : `${name} is shared with your care teams.`) | (name, privateNow) =&gt; (privateNow ? `${name} ahora es privada.` : `${name} se comparte con tus equipos de atención.`) |
| apps/patient-portal/src/content/care-team-copy.ts:108 / `copy.privacyError` | We could not save that change. Your setting is back to what it was. | No pudimos guardar ese cambio. Tu ajuste volvió a como estaba. |
| apps/patient-portal/src/content/care-team-copy.ts:109 / `copy.close` | Close | Cerrar |
| apps/patient-portal/src/content/symptom-history-copy.ts:51 / `copy.heading` | My symptoms | Mis síntomas |
| apps/patient-portal/src/content/symptom-history-copy.ts:52 / `copy.loading` | Loading your symptom reports… | Cargando tus reportes de síntomas… |
| apps/patient-portal/src/content/symptom-history-copy.ts:53 / `copy.errorTitle` | Could not load your symptoms | No se pudieron cargar tus síntomas |
| apps/patient-portal/src/content/symptom-history-copy.ts:54 / `copy.errorDetail` | Your reports are safe. Try again in a moment. | Tus reportes están a salvo. Intenta de nuevo en un momento. |
| apps/patient-portal/src/content/symptom-history-copy.ts:55 / `copy.emptyTitle` | No confirmed symptom reports yet | Aún no hay reportes de síntomas confirmados |
| apps/patient-portal/src/content/symptom-history-copy.ts:57 / `copy.emptyDetail` | When you confirm a symptom report with Nora, it will appear here with what happened next. | Cuando confirmes un reporte de síntomas con Nora, aparecerá aquí con lo que sucedió después. |
| apps/patient-portal/src/content/symptom-history-copy.ts:58 / `copy.more` | Showing your most recent reports. | Se muestran tus reportes más recientes. |
| apps/patient-portal/src/content/symptom-history-copy.ts:59 / `copy.severity` | (value: number &#124; null) =&gt; value === null ? "Severity not given" : `Severity ${value} of 10` | (value) =&gt; value === null ? "Intensidad no indicada" : `Intensidad ${value} de 10` |
| apps/patient-portal/src/content/symptom-history-copy.ts:61 / `copy.rowLabel` | (symptom: string, severity: string, date: string) =&gt; `${symptom}, ${severity}, ${date}` | (symptom, severity, date) =&gt; `${symptom}, ${severity}, ${date}` |
| apps/patient-portal/src/content/symptom-history-copy.ts:63 / `copy.status.reported` | Reported | Reportado |
| apps/patient-portal/src/content/symptom-history-copy.ts:64 / `copy.status.not_sent` | Not sent: no care team yet | No enviado: aún no tienes equipo de atención |
| apps/patient-portal/src/content/symptom-history-copy.ts:65 / `copy.status.shared` | Sent to your care team | Enviado a tu equipo de atención |
| apps/patient-portal/src/content/symptom-history-copy.ts:66 / `copy.status.reviewed` | Reviewed | Revisado |
| apps/patient-portal/src/content/symptom-history-copy.ts:68 / `copy.detailTitle` | Symptom report | Reporte de síntoma |
| apps/patient-portal/src/content/symptom-history-copy.ts:69 / `copy.back` | Back to symptoms | Volver a síntomas |
| apps/patient-portal/src/content/symptom-history-copy.ts:70 / `copy.notFoundTitle` | Report not found | Reporte no encontrado |
| apps/patient-portal/src/content/symptom-history-copy.ts:71 / `copy.notFoundDetail` | This report is not available to you. | Este reporte no está disponible para ti. |
| apps/patient-portal/src/content/symptom-history-copy.ts:72 / `copy.answers` | What you confirmed | Lo que confirmaste |
| apps/patient-portal/src/content/symptom-history-copy.ts:73 / `copy.answersNote` | Shown as you confirmed it, in the language you used. | Se muestra como lo confirmaste, en el idioma que usaste. |
| apps/patient-portal/src/content/symptom-history-copy.ts:74 / `copy.noAnswers` | No answers were saved with this report. | No se guardaron respuestas con este reporte. |
| apps/patient-portal/src/content/symptom-history-copy.ts:75 / `copy.whenReported` | Confirmed | Confirmado |
| apps/patient-portal/src/content/symptom-history-copy.ts:76 / `copy.onset` | Started | Empezó |
| apps/patient-portal/src/content/symptom-history-copy.ts:77 / `copy.duration` | Lasted | Duró |
| apps/patient-portal/src/content/symptom-history-copy.ts:78 / `copy.progress` | What happened next | Qué pasó después |
| apps/patient-portal/src/content/symptom-history-copy.ts:80 / `copy.events.reported` | You confirmed this report | Confirmaste este reporte |
| apps/patient-portal/src/content/symptom-history-copy.ts:81 / `copy.events.shared_with_care_team` | Sent to your care team | Enviado a tu equipo de atención |
| apps/patient-portal/src/content/symptom-history-copy.ts:83 / `copy.events.not_sent_no_care_team` | Not sent: you have no care team yet. Contact your clinic. | No enviado: aún no tienes un equipo de atención. Comunícate con tu clínica. |
| apps/patient-portal/src/content/symptom-history-copy.ts:84 / `copy.events.flagged_urgent` | Marked for urgent review by your care team | Marcado para que tu equipo de atención lo revise con urgencia |
| apps/patient-portal/src/content/symptom-history-copy.ts:85 / `copy.events.reviewed` | (name: string &#124; null) =&gt; name ? `Reviewed by ${name}` : "Reviewed by your care team" | (name) =&gt; name ? `Revisado por ${name}` : "Revisado por tu equipo de atención" |
| apps/patient-portal/src/content/symptom-history-copy.ts:89 / `copy.disclaimer` | This is a record of what you reported. It is not a diagnosis. In an emergency, call 911. | Este es un registro de lo que reportaste. No es un diagnóstico. En una emergencia, llama al 911. |
| apps/patient-portal/src/content/symptom-history-copy.ts:90 / `copy.retry` | Try again | Intentar de nuevo |
| apps/patient-portal/src/content/symptom-history-copy.ts:51 / `getSymptomHistoryCopy.heading` | My symptoms | Mis síntomas |
| apps/patient-portal/src/content/symptom-history-copy.ts:52 / `getSymptomHistoryCopy.loading` | Loading your symptom reports… | Cargando tus reportes de síntomas… |
| apps/patient-portal/src/content/symptom-history-copy.ts:53 / `getSymptomHistoryCopy.errorTitle` | Could not load your symptoms | No se pudieron cargar tus síntomas |
| apps/patient-portal/src/content/symptom-history-copy.ts:54 / `getSymptomHistoryCopy.errorDetail` | Your reports are safe. Try again in a moment. | Tus reportes están a salvo. Intenta de nuevo en un momento. |
| apps/patient-portal/src/content/symptom-history-copy.ts:55 / `getSymptomHistoryCopy.emptyTitle` | No confirmed symptom reports yet | Aún no hay reportes de síntomas confirmados |
| apps/patient-portal/src/content/symptom-history-copy.ts:57 / `getSymptomHistoryCopy.emptyDetail` | When you confirm a symptom report with Nora, it will appear here with what happened next. | Cuando confirmes un reporte de síntomas con Nora, aparecerá aquí con lo que sucedió después. |
| apps/patient-portal/src/content/symptom-history-copy.ts:58 / `getSymptomHistoryCopy.more` | Showing your most recent reports. | Se muestran tus reportes más recientes. |
| apps/patient-portal/src/content/symptom-history-copy.ts:59 / `getSymptomHistoryCopy.severity` | (value: number &#124; null) =&gt; value === null ? "Severity not given" : `Severity ${value} of 10` | (value) =&gt; value === null ? "Intensidad no indicada" : `Intensidad ${value} de 10` |
| apps/patient-portal/src/content/symptom-history-copy.ts:61 / `getSymptomHistoryCopy.rowLabel` | (symptom: string, severity: string, date: string) =&gt; `${symptom}, ${severity}, ${date}` | (symptom, severity, date) =&gt; `${symptom}, ${severity}, ${date}` |
| apps/patient-portal/src/content/symptom-history-copy.ts:63 / `getSymptomHistoryCopy.status.reported` | Reported | Reportado |
| apps/patient-portal/src/content/symptom-history-copy.ts:64 / `getSymptomHistoryCopy.status.not_sent` | Not sent: no care team yet | No enviado: aún no tienes equipo de atención |
| apps/patient-portal/src/content/symptom-history-copy.ts:65 / `getSymptomHistoryCopy.status.shared` | Sent to your care team | Enviado a tu equipo de atención |
| apps/patient-portal/src/content/symptom-history-copy.ts:66 / `getSymptomHistoryCopy.status.reviewed` | Reviewed | Revisado |
| apps/patient-portal/src/content/symptom-history-copy.ts:68 / `getSymptomHistoryCopy.detailTitle` | Symptom report | Reporte de síntoma |
| apps/patient-portal/src/content/symptom-history-copy.ts:69 / `getSymptomHistoryCopy.back` | Back to symptoms | Volver a síntomas |
| apps/patient-portal/src/content/symptom-history-copy.ts:70 / `getSymptomHistoryCopy.notFoundTitle` | Report not found | Reporte no encontrado |
| apps/patient-portal/src/content/symptom-history-copy.ts:71 / `getSymptomHistoryCopy.notFoundDetail` | This report is not available to you. | Este reporte no está disponible para ti. |
| apps/patient-portal/src/content/symptom-history-copy.ts:72 / `getSymptomHistoryCopy.answers` | What you confirmed | Lo que confirmaste |
| apps/patient-portal/src/content/symptom-history-copy.ts:73 / `getSymptomHistoryCopy.answersNote` | Shown as you confirmed it, in the language you used. | Se muestra como lo confirmaste, en el idioma que usaste. |
| apps/patient-portal/src/content/symptom-history-copy.ts:74 / `getSymptomHistoryCopy.noAnswers` | No answers were saved with this report. | No se guardaron respuestas con este reporte. |
| apps/patient-portal/src/content/symptom-history-copy.ts:75 / `getSymptomHistoryCopy.whenReported` | Confirmed | Confirmado |
| apps/patient-portal/src/content/symptom-history-copy.ts:76 / `getSymptomHistoryCopy.onset` | Started | Empezó |
| apps/patient-portal/src/content/symptom-history-copy.ts:77 / `getSymptomHistoryCopy.duration` | Lasted | Duró |
| apps/patient-portal/src/content/symptom-history-copy.ts:78 / `getSymptomHistoryCopy.progress` | What happened next | Qué pasó después |
| apps/patient-portal/src/content/symptom-history-copy.ts:80 / `getSymptomHistoryCopy.events.reported` | You confirmed this report | Confirmaste este reporte |
| apps/patient-portal/src/content/symptom-history-copy.ts:81 / `getSymptomHistoryCopy.events.shared_with_care_team` | Sent to your care team | Enviado a tu equipo de atención |
| apps/patient-portal/src/content/symptom-history-copy.ts:83 / `getSymptomHistoryCopy.events.not_sent_no_care_team` | Not sent: you have no care team yet. Contact your clinic. | No enviado: aún no tienes un equipo de atención. Comunícate con tu clínica. |
| apps/patient-portal/src/content/symptom-history-copy.ts:84 / `getSymptomHistoryCopy.events.flagged_urgent` | Marked for urgent review by your care team | Marcado para que tu equipo de atención lo revise con urgencia |
| apps/patient-portal/src/content/symptom-history-copy.ts:85 / `getSymptomHistoryCopy.events.reviewed` | (name: string &#124; null) =&gt; name ? `Reviewed by ${name}` : "Reviewed by your care team" | (name) =&gt; name ? `Revisado por ${name}` : "Revisado por tu equipo de atención" |
| apps/patient-portal/src/content/symptom-history-copy.ts:89 / `getSymptomHistoryCopy.disclaimer` | This is a record of what you reported. It is not a diagnosis. In an emergency, call 911. | Este es un registro de lo que reportaste. No es un diagnóstico. En una emergencia, llama al 911. |
| apps/patient-portal/src/content/symptom-history-copy.ts:90 / `getSymptomHistoryCopy.retry` | Try again | Intentar de nuevo |
| apps/patient-portal/src/content/visits-copy.ts:111 / `copy.chatHelp.title` | Need help with a visit? | ¿Necesitas ayuda con una cita? |
| apps/patient-portal/src/content/visits-copy.ts:113 / `copy.chatHelp.description` | Open chat for general guidance. Use Visits to choose or change appointment times. | Abre el chat para orientación general. Usa Citas para elegir o cambiar los horarios. |
| apps/patient-portal/src/content/visits-copy.ts:114 / `copy.chatHelp.open` | Open chat | Abrir chat |
| apps/patient-portal/src/content/visits-copy.ts:116 / `copy.minutes` | min | min |
| apps/patient-portal/src/content/visits-copy.ts:117 / `copy.preparationNotes` | Preparation notes | Notas de preparación |
| apps/patient-portal/src/content/visits-copy.ts:118 / `copy.upcomingSummary.one` | upcoming visit | próxima cita |
| apps/patient-portal/src/content/visits-copy.ts:118 / `copy.upcomingSummary.other` | upcoming visits | próximas citas |
| apps/patient-portal/src/content/visits-copy.ts:120 / `copy.types.follow_up` | Follow-up | Seguimiento |
| apps/patient-portal/src/content/visits-copy.ts:121 / `copy.types.initial` | First visit | Primera consulta |
| apps/patient-portal/src/content/visits-copy.ts:122 / `copy.types.routine` | Routine check | Revisión de rutina |
| apps/patient-portal/src/content/visits-copy.ts:123 / `copy.types.urgent` | Urgent | Urgente |
| apps/patient-portal/src/content/visits-copy.ts:124 / `copy.types.pre_op` | Pre-operative | Preoperatoria |
| apps/patient-portal/src/content/visits-copy.ts:126 / `copy.offerTitle` | Your clinician offered these times | Tu profesional clínico ofreció estos horarios |
| apps/patient-portal/src/content/visits-copy.ts:127 / `copy.choose` | Choose this time | Elegir este horario |
| apps/patient-portal/src/content/visits-copy.ts:129 / `copy.offerDecline.label` | Reason for declining (optional) | Motivo del rechazo (opcional) |
| apps/patient-portal/src/content/visits-copy.ts:130 / `copy.offerDecline.placeholder` | Let your care team know why | Explica el motivo a tu equipo de atención |
| apps/patient-portal/src/content/visits-copy.ts:131 / `copy.offerDecline.confirm` | Decline offer | Rechazar propuesta |
| apps/patient-portal/src/content/visits-copy.ts:133 / `copy.declineOffer` | Decline these times | Rechazar estos horarios |
| apps/patient-portal/src/content/visits-copy.ts:134 / `copy.differentTimes` | Request different times | Solicitar otros horarios |
| apps/patient-portal/src/content/visits-copy.ts:135 / `copy.title` | Visits | Citas |
| apps/patient-portal/src/content/visits-copy.ts:136 / `copy.subtitle` | Review and confirm appointments from your care team. | Revisa y confirma las citas propuestas por tu equipo de atención. |
| apps/patient-portal/src/content/visits-copy.ts:137 / `copy.loading` | Loading your visits... | Cargando tus citas... |
| apps/patient-portal/src/content/visits-copy.ts:138 / `copy.loadingSettings` | Loading your visit settings... | Cargando la configuración de tus citas... |
| apps/patient-portal/src/content/visits-copy.ts:139 / `copy.loadError` | Could not load your visits | No se pudieron cargar tus citas |
| apps/patient-portal/src/content/visits-copy.ts:140 / `copy.loadErrorDetail` | Please try loading your visits again. | Intenta cargar tus citas de nuevo. |
| apps/patient-portal/src/content/visits-copy.ts:142 / `copy.actionError` | Could not update this visit. Refresh your visits and try again. | No se pudo actualizar esta cita. Actualiza tus citas e inténtalo de nuevo. |
| apps/patient-portal/src/content/visits-copy.ts:144 / `copy.conflictError` | This time overlaps another booked visit. Choose another time or ask your care team for different times. | Este horario se empalma con otra cita programada. Elige otro horario o solicita otros horarios a tu equipo de atención. |
| apps/patient-portal/src/content/visits-copy.ts:146 / `copy.expiredError` | This offer has expired. Refresh your visits to see the available times. | Esta propuesta venció. Actualiza tus citas para ver los horarios disponibles. |
| apps/patient-portal/src/content/visits-copy.ts:148 / `copy.unavailableError` | This appointment is no longer available. Refresh your visits before trying again. | Esta cita ya no está disponible. Actualiza tus citas antes de intentarlo de nuevo. |
| apps/patient-portal/src/content/visits-copy.ts:150 / `copy.pastError` | This appointment time has passed. Refresh your visits and choose a future time. | El horario de esta cita ya pasó. Actualiza tus citas y elige un horario futuro. |
| apps/patient-portal/src/content/visits-copy.ts:151 / `copy.availableUntil` | Available until | Disponible hasta |
| apps/patient-portal/src/content/visits-copy.ts:153 / `copy.responseSavedRefreshError` | Your response was saved, but the latest visits could not be loaded. Refresh your visits to check the full offer. | Tu respuesta se guardó, pero no se pudieron cargar las citas más recientes. Actualiza tus citas para revisar la propuesta completa. |
| apps/patient-portal/src/content/visits-copy.ts:155 / `copy.expiredDetail` | This time is no longer available. Your care team can offer new times. | Este horario ya no está disponible. Tu equipo de atención puede ofrecer nuevos horarios. |
| apps/patient-portal/src/content/visits-copy.ts:156 / `copy.retry` | Try again | Intentar de nuevo |
| apps/patient-portal/src/content/visits-copy.ts:157 / `copy.refreshVisits` | Refresh visits | Actualizar citas |
| apps/patient-portal/src/content/visits-copy.ts:159 / `copy.fallback` | Your saved timezone is unavailable. Times are shown in UTC. | Tu zona horaria guardada no está disponible. Los horarios se muestran en UTC. |
| apps/patient-portal/src/content/visits-copy.ts:160 / `copy.emptyTitle` | No visits yet | Aún no tienes citas |
| apps/patient-portal/src/content/visits-copy.ts:162 / `copy.emptyDetail` | When your clinician proposes a visit, it will appear here for you to accept, decline, or request a different time. | Cuando tu profesional clínico proponga una cita, aparecerá aquí para que la aceptes, la rechaces o solicites otro horario. |
| apps/patient-portal/src/content/visits-copy.ts:163 / `copy.proposed` | Awaiting your response | Esperando tu respuesta |
| apps/patient-portal/src/content/visits-copy.ts:164 / `copy.upcoming` | Upcoming | Próximas citas |
| apps/patient-portal/src/content/visits-copy.ts:165 / `copy.waiting` | Waiting on your care team | Esperando a tu equipo de atención |
| apps/patient-portal/src/content/visits-copy.ts:166 / `copy.past` | Past &amp; other | Citas pasadas y otras |
| apps/patient-portal/src/content/visits-copy.ts:167 / `copy.with` | With | Con |
| apps/patient-portal/src/content/visits-copy.ts:168 / `copy.atClinic` | (clinic: string) =&gt; `at ${clinic}` | (clinic: string) =&gt; `en ${clinic}` |
| apps/patient-portal/src/content/visits-copy.ts:169 / `copy.note` | Your note: | Tu nota: |
| apps/patient-portal/src/content/visits-copy.ts:171 / `copy.cancelledByCare` | Your care team cancelled this visit. | Tu equipo de atención canceló esta cita. |
| apps/patient-portal/src/content/visits-copy.ts:172 / `copy.cancelReasonLabel` | Reason: | Motivo: |
| apps/patient-portal/src/content/visits-copy.ts:174 / `copy.cancelReasons.clinician_unavailable` | Your clinician is unavailable | Tu profesional clínico no está disponible |
| apps/patient-portal/src/content/visits-copy.ts:175 / `copy.cancelReasons.clinic_closed` | The clinic is closed | La clínica está cerrada |
| apps/patient-portal/src/content/visits-copy.ts:176 / `copy.cancelReasons.patient_request` | You asked to cancel | Pediste cancelar la cita |
| apps/patient-portal/src/content/visits-copy.ts:177 / `copy.cancelReasons.scheduling_error` | The visit was scheduled by mistake | La cita se programó por error |
| apps/patient-portal/src/content/visits-copy.ts:178 / `copy.cancelReasons.other` | Other reason | Otro motivo |
| apps/patient-portal/src/content/visits-copy.ts:180 / `copy.accept` | Accept | Aceptar |
| apps/patient-portal/src/content/visits-copy.ts:181 / `copy.decline` | Decline | Rechazar |
| apps/patient-portal/src/content/visits-copy.ts:182 / `copy.cancel` | Cancel | Cancelar |
| apps/patient-portal/src/content/visits-copy.ts:183 / `copy.cancelVisit` | Cancel visit | Cancelar cita |
| apps/patient-portal/src/content/visits-copy.ts:184 / `copy.back` | Back | Volver |
| apps/patient-portal/src/content/visits-copy.ts:185 / `copy.request` | Request a different time | Solicitar otro horario |
| apps/patient-portal/src/content/visits-copy.ts:186 / `copy.invalidDate` | Appointment time unavailable | Horario de la cita no disponible |
| apps/patient-portal/src/content/visits-copy.ts:188 / `copy.statuses.withdrawn` | Withdrawn | Retirada |
| apps/patient-portal/src/content/visits-copy.ts:189 / `copy.statuses.expired` | Expired | Vencida |
| apps/patient-portal/src/content/visits-copy.ts:190 / `copy.statuses.proposed` | Proposed | Propuesta |
| apps/patient-portal/src/content/visits-copy.ts:191 / `copy.statuses.confirmed` | Confirmed | Confirmada |
| apps/patient-portal/src/content/visits-copy.ts:192 / `copy.statuses.scheduled` | Scheduled | Programada |
| apps/patient-portal/src/content/visits-copy.ts:193 / `copy.statuses.declined` | Declined | Rechazada |
| apps/patient-portal/src/content/visits-copy.ts:194 / `copy.statuses.alternative_requested` | Change requested | Cambio solicitado |
| apps/patient-portal/src/content/visits-copy.ts:195 / `copy.statuses.cancelled` | Cancelled | Cancelada |
| apps/patient-portal/src/content/visits-copy.ts:196 / `copy.statuses.completed` | Completed | Completada |
| apps/patient-portal/src/content/visits-copy.ts:197 / `copy.statuses.no_show` | Missed | No asististe |
| apps/patient-portal/src/content/visits-copy.ts:201 / `copy.compose.request_alternative.label` | What times work better? (optional) | ¿Qué horarios te convienen más? (opcional) |
| apps/patient-portal/src/content/visits-copy.ts:203 / `copy.compose.request_alternative.placeholder` | e.g. mornings, or after next week | Por ejemplo, por las mañanas o después de la próxima semana |
| apps/patient-portal/src/content/visits-copy.ts:204 / `copy.compose.request_alternative.confirm` | Send request | Enviar solicitud |
| apps/patient-portal/src/content/visits-copy.ts:207 / `copy.compose.cancel.label` | Reason for cancelling (optional) | Motivo de la cancelación (opcional) |
| apps/patient-portal/src/content/visits-copy.ts:208 / `copy.compose.cancel.placeholder` | Let your care team know why | Explica el motivo a tu equipo de atención |
| apps/patient-portal/src/content/visits-copy.ts:209 / `copy.compose.cancel.confirm` | Confirm cancellation | Confirmar cancelación |
| apps/patient-portal/src/content/symptom-intake-copy.ts:28 / `copy.offerPrompt` | Would you like me to note this for your care team? I’ll ask a few quick questions here. | ¿Quieres que lo anote para tu equipo de atención? Te haré unas preguntas rápidas aquí. |
| apps/patient-portal/src/content/symptom-intake-copy.ts:28 / `copy.offerYes` | Yes, let’s do it | Sí, hagámoslo |
| apps/patient-portal/src/content/symptom-intake-copy.ts:28 / `copy.offerNo` | Not now | Ahora no |
| apps/patient-portal/src/content/symptom-intake-copy.ts:29 / `copy.privateTag` | Private until you confirm | Privado hasta que confirmes |
| apps/patient-portal/src/content/symptom-intake-copy.ts:29 / `copy.offerStarting` | Opening your private note… | Abriendo tu nota privada… |
| apps/patient-portal/src/content/symptom-intake-copy.ts:30 / `copy.title` | Draft — not submitted | Borrador — no enviado |
| apps/patient-portal/src/content/symptom-intake-copy.ts:30 / `copy.start` | Start a symptom draft | Iniciar un borrador de síntomas |
| apps/patient-portal/src/content/symptom-intake-copy.ts:30 / `copy.intro` | Your answers here remain private until you confirm. Your initial Nora message remains in chat history. | Tus respuestas aquí son privadas hasta que confirmes. Tu mensaje inicial a Nora permanece en el historial del chat. |
| apps/patient-portal/src/content/symptom-intake-copy.ts:31 / `copy.answerPrompt` | Type or speak your answer below. You can say “not sure” or “skip”. | Escribe o di tu respuesta abajo. Puedes decir “no sé” o “prefiero no responder”. |
| apps/patient-portal/src/content/symptom-intake-copy.ts:32 / `copy.suggestion` | From your message | De tu mensaje |
| apps/patient-portal/src/content/symptom-intake-copy.ts:32 / `copy.useSuggestion` | Use this answer | Usar esta respuesta |
| apps/patient-portal/src/content/symptom-intake-copy.ts:32 / `copy.detailEntry` | Enter detailed fields instead | Ingresar campos detallados |
| apps/patient-portal/src/content/symptom-intake-copy.ts:33 / `copy.listen` | Listen | Escuchar |
| apps/patient-portal/src/content/symptom-intake-copy.ts:33 / `copy.reviewFirst` | Review the summary, then use the confirmation controls to share. A spoken reply cannot submit it. | Revisa el resumen y usa los controles de confirmación para compartirlo. Una respuesta hablada no lo envía. |
| apps/patient-portal/src/content/symptom-intake-copy.ts:34 / `copy.productReported` | Products reported by you — unverified; not added to your medication list | Productos reportados por ti — sin verificar; no se agregaron a tu lista de medicamentos |
| apps/patient-portal/src/content/symptom-intake-copy.ts:35 / `copy.recordSource` | Approved record source | Fuente aprobada del expediente |
| apps/patient-portal/src/content/symptom-intake-copy.ts:35 / `copy.excerptSource` | Source document | Documento fuente |
| apps/patient-portal/src/content/symptom-intake-copy.ts:35 / `copy.pendingAnswer` | Your answer — not yet verified as saved | Tu respuesta — aún no confirmamos que se guardó |
| apps/patient-portal/src/content/symptom-intake-copy.ts:36 / `copy.editReply` | Edit this response | Editar esta respuesta |
| apps/patient-portal/src/content/symptom-intake-copy.ts:36 / `copy.existingDraft` | You have an unfinished draft in this conversation. Continue or cancel it before starting another. | Tienes un borrador sin terminar en esta conversación. Continúalo o cancélalo antes de iniciar otro. |
| apps/patient-portal/src/content/symptom-intake-copy.ts:37 / `copy.urgentReview` | Your high-severity answer has been queued for care-team review. This does not mean someone has read it. Messages are not continuously monitored. | Tu respuesta de alta intensidad está en espera de revisión por tu equipo de atención. Esto no significa que alguien la haya leído. Los mensajes no se supervisan continuamente. |
| apps/patient-portal/src/content/symptom-intake-copy.ts:38 / `copy.loading` | Loading your draft… | Cargando tu borrador… |
| apps/patient-portal/src/content/symptom-intake-copy.ts:38 / `copy.unavailable` | Guided intake is unavailable. Reload the saved state to check any prior action. | La captura guiada no está disponible. Vuelve a cargar el estado guardado para verificar una acción anterior. |
| apps/patient-portal/src/content/symptom-intake-copy.ts:39 / `copy.error` | We could not verify this action. Reload the saved state before retrying. | No pudimos verificar esta acción. Vuelve a cargar el estado guardado antes de reintentar. |
| apps/patient-portal/src/content/symptom-intake-copy.ts:39 / `copy.reload` | Reload saved state | Volver a cargar el estado guardado |
| apps/patient-portal/src/content/symptom-intake-copy.ts:39 / `copy.retry` | Retry the same action | Reintentar la misma acción |
| apps/patient-portal/src/content/symptom-intake-copy.ts:40 / `copy.save` | Save answer | Guardar respuesta |
| apps/patient-portal/src/content/symptom-intake-copy.ts:40 / `copy.unknown` | I don’t know | No sé |
| apps/patient-portal/src/content/symptom-intake-copy.ts:40 / `copy.declined` | Prefer not to answer | Prefiero no responder |
| apps/patient-portal/src/content/symptom-intake-copy.ts:40 / `copy.edit` | Edit | Editar |
| apps/patient-portal/src/content/symptom-intake-copy.ts:40 / `copy.review` | Review before sharing | Revisar antes de compartir |
| apps/patient-portal/src/content/symptom-intake-copy.ts:40 / `copy.cancel` | Cancel draft | Cancelar borrador |
| apps/patient-portal/src/content/symptom-intake-copy.ts:41 / `copy.confirm` | Confirm and share with my care team | Confirmar y compartir con mi equipo clínico |
| apps/patient-portal/src/content/symptom-intake-copy.ts:41 / `copy.consent` | I reviewed this preview and want to share it with my care team. | Revisé esta vista previa y quiero compartirla con mi equipo clínico. |
| apps/patient-portal/src/content/symptom-intake-copy.ts:42 / `copy.reported` | What you reported | Lo que reportaste |
| apps/patient-portal/src/content/symptom-intake-copy.ts:42 / `copy.context` | Relevant information from your record | Información relevante de tu expediente |
| apps/patient-portal/src/content/symptom-intake-copy.ts:42 / `copy.summary` | Summary for your care team | Resumen para tu equipo clínico |
| apps/patient-portal/src/content/symptom-intake-copy.ts:42 / `copy.emptyContext` | No relevant record context was used. | No se usó información relevante del expediente. |
| apps/patient-portal/src/content/symptom-intake-copy.ts:43 / `copy.saved` | Report saved for care-team review | Reporte guardado para revisión del equipo clínico |
| apps/patient-portal/src/content/symptom-intake-copy.ts:43 / `copy.cancelled` | Draft cancelled. Your chat history was not deleted. | Borrador cancelado. No se eliminó tu historial del chat. |
| apps/patient-portal/src/content/symptom-intake-copy.ts:44 / `copy.interrupted` | Intake interrupted for safety | Captura interrumpida por seguridad |
| apps/patient-portal/src/content/symptom-intake-copy.ts:44 / `copy.pending` | The safety save could not be verified. | No se pudo verificar el guardado de seguridad. |
| apps/patient-portal/src/content/symptom-intake-copy.ts:45 / `copy.timezone` | Saved patient timezone | Zona horaria guardada del paciente |
| apps/patient-portal/src/content/symptom-intake-copy.ts:45 / `copy.fallback` | UTC fallback — saved timezone unavailable | Se usa UTC porque la zona horaria guardada no está disponible |
| apps/patient-portal/src/content/symptom-intake-copy.ts:45 / `copy.progress` | Questions resolved | Preguntas resueltas |
| apps/patient-portal/src/content/symptom-intake-copy.ts:45 / `copy.value` | Your answer | Tu respuesta |
| apps/patient-portal/src/content/symptom-intake-copy.ts:46 / `copy.yes` | Yes | Sí |
| apps/patient-portal/src/content/symptom-intake-copy.ts:46 / `copy.no` | No | No |
| apps/patient-portal/src/content/symptom-intake-copy.ts:46 / `copy.productConcern` | I am concerned about a medicine or other product | Me preocupa algún medicamento u otro producto |
| apps/patient-portal/src/content/symptom-intake-copy.ts:46 / `copy.name` | Product name | Nombre del producto |
| apps/patient-portal/src/content/symptom-intake-copy.ts:46 / `copy.strength` | Strength | Concentración |
| apps/patient-portal/src/content/symptom-intake-copy.ts:46 / `copy.dose` | Dose | Dosis |
| apps/patient-portal/src/content/symptom-intake-copy.ts:46 / `copy.route` | Route | Vía |
| apps/patient-portal/src/content/symptom-intake-copy.ts:47 / `copy.indication` | Reason for use | Motivo de uso |
| apps/patient-portal/src/content/symptom-intake-copy.ts:47 / `copy.startDate` | Started (your words) | Inicio (tus palabras) |
| apps/patient-portal/src/content/symptom-intake-copy.ts:47 / `copy.stop` | Stopped (your words) | Suspensión (tus palabras) |
| apps/patient-portal/src/content/symptom-intake-copy.ts:47 / `copy.change` | Changed (your words) | Cambio (tus palabras) |
| apps/patient-portal/src/content/symptom-intake-copy.ts:48 / `copy.states.answered` | Answered | Respondida |
| apps/patient-portal/src/content/symptom-intake-copy.ts:48 / `copy.states.unknown` | Unknown | No sé |
| apps/patient-portal/src/content/symptom-intake-copy.ts:48 / `copy.states.declined` | Declined | Prefiero no responder |
| apps/patient-portal/src/content/symptom-intake-copy.ts:48 / `copy.states.not_asked` | Not asked | No preguntada |
| apps/patient-portal/src/content/symptom-intake-copy.ts:48 / `copy.states.not_applicable` | Not applicable | No aplica |
| apps/patient-portal/src/content/medication-confirmation-copy.ts:55 / `copy.eyebrow` | A question about your medicine | Una pregunta sobre tu medicamento |
| apps/patient-portal/src/content/medication-confirmation-copy.ts:56 / `copy.from` | (clinician, specialty) =&gt; (specialty ? `From ${clinician}, ${specialty}` : `From ${clinician}`) | (clinician, specialty) =&gt; (specialty ? `De ${clinician}, ${specialty}` : `De ${clinician}`) |
| apps/patient-portal/src/content/medication-confirmation-copy.ts:57 / `copy.question` | (description) =&gt; `Are you still taking ${description}?` | (description) =&gt; `¿Sigues tomando ${description}?` |
| apps/patient-portal/src/content/medication-confirmation-copy.ts:59 / `copy.answers.yes` | Yes | Sí |
| apps/patient-portal/src/content/medication-confirmation-copy.ts:60 / `copy.answers.stopped` | No, I stopped | No, lo dejé |
| apps/patient-portal/src/content/medication-confirmation-copy.ts:61 / `copy.answers.changed` | It changed | Cambió |
| apps/patient-portal/src/content/medication-confirmation-copy.ts:62 / `copy.answers.unsure` | Not sure | No lo sé |
| apps/patient-portal/src/content/medication-confirmation-copy.ts:64 / `copy.changedLabel` | What changed? | ¿Qué cambió? |
| apps/patient-portal/src/content/medication-confirmation-copy.ts:65 / `copy.changedHint` | For example, a different amount or time of day. | Por ejemplo, otra cantidad u otra hora del día. |
| apps/patient-portal/src/content/medication-confirmation-copy.ts:66 / `copy.characters` | (used, max) =&gt; `${used} of ${max} characters` | (used, max) =&gt; `${used} de ${max} caracteres` |
| apps/patient-portal/src/content/medication-confirmation-copy.ts:68 / `copy.privacy` | Your answer goes to your care team. It does not change your medicines or your reminders. Keep taking your medicines as prescribed until your care team tells you otherwise. | Tu respuesta llega a tu equipo de atención. No cambia tus medicamentos ni tus recordatorios. Sigue tomando tus medicamentos como te los recetaron hasta que tu equipo de atención te indique otra cosa. |
| apps/patient-portal/src/content/medication-confirmation-copy.ts:69 / `copy.send` | Send answer | Enviar respuesta |
| apps/patient-portal/src/content/medication-confirmation-copy.ts:70 / `copy.sending` | Sending… | Enviando… |
| apps/patient-portal/src/content/medication-confirmation-copy.ts:71 / `copy.thanks` | Thank you | Gracias |
| apps/patient-portal/src/content/medication-confirmation-copy.ts:72 / `copy.thanksDetail` | Your care team will see your answer. | Tu equipo de atención verá tu respuesta. |
| apps/patient-portal/src/content/medication-confirmation-copy.ts:74 / `copy.errors.answered` | This question was already answered. | Esta pregunta ya se respondió. |
| apps/patient-portal/src/content/medication-confirmation-copy.ts:75 / `copy.errors.expired` | This question has expired. Your care team can ask again. | Esta pregunta venció. Tu equipo de atención puede volver a preguntar. |
| apps/patient-portal/src/content/medication-confirmation-copy.ts:76 / `copy.errors.notFound` | This question is no longer available. | Esta pregunta ya no está disponible. |
| apps/patient-portal/src/content/medication-confirmation-copy.ts:77 / `copy.errors.unavailable` | We could not send your answer. Check your connection and try again. | No pudimos enviar tu respuesta. Revisa tu conexión e inténtalo de nuevo. |
| apps/patient-portal/src/content/medication-confirmation-copy.ts:78 / `copy.errors.other` | We could not send your answer. Try again in a moment. | No pudimos enviar tu respuesta. Inténtalo de nuevo en un momento. |
| apps/patient-portal/src/content/medication-confirmation-copy.ts:80 / `copy.group` | (medicine) =&gt; `Your answer about ${medicine}` | (medicine) =&gt; `Tu respuesta sobre ${medicine}` |
| apps/patient-portal/src/content/reply-sources-copy.ts:14 / `copy.summary` | Sources | Fuentes |
| apps/patient-portal/src/content/reply-sources-copy.ts:15 / `copy.loading` | Loading sources… | Cargando fuentes… |
| apps/patient-portal/src/content/reply-sources-copy.ts:16 / `copy.failed` | Sources could not be loaded. Close and open to try again. | No se pudieron cargar las fuentes. Cierra y vuelve a abrir para intentarlo otra vez. |
| apps/patient-portal/src/content/reply-sources-copy.ts:17 / `copy.page` | (pages: number[]) =&gt; (pages.length === 1 ? `page ${pages[0]}` : `pages ${pages.join(", ")}`) | (pages: number[]) =&gt; (pages.length === 1 ? `página ${pages[0]}` : `páginas ${pages.join(", ")}`) |
| apps/patient-portal/src/content/reply-sources-copy.ts:18 / `copy.record` | Your health record in this app | Tu expediente de salud en esta app |
| apps/patient-portal/src/content/reply-sources-copy.ts:19 / `copy.untitled` | Document | Documento |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:74 / `copy.title` | Profile | Perfil |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:75 / `copy.subtitle` | Manage your account and linked clinics. | Administra tu cuenta y las clínicas vinculadas. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:76 / `copy.loadTitle` | Unable to load your profile | No se pudo cargar tu perfil |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:77 / `copy.loadError` | We couldn’t load your account. Please try again. | No pudimos cargar tu cuenta. Inténtalo de nuevo. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:78 / `copy.retry` | Try again | Intentar de nuevo |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:80 / `copy.onboarding` | No active care team is linked yet. Add your care team and enter the invite code your clinician gave you. | Aún no tienes un equipo de atención activo vinculado. Agrega tu equipo e ingresa el código de invitación que te dio tu clínico. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:81 / `copy.patientAccount` | Patient account | Cuenta del paciente |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:82 / `copy.details` | Profile details | Detalles del perfil |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:83 / `copy.personal` | Personal information | Información personal |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:84 / `copy.editing` | Editing | Editando |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:85 / `copy.editProfile` | Edit profile | Editar perfil |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:86 / `copy.edit` | Edit | Editar |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:87 / `copy.firstName` | First name | Nombre |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:88 / `copy.lastName` | Last name | Apellidos |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:89 / `copy.language` | Preferred language | Idioma preferido |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:91 / `copy.languageHelp` | Saving this changes the app language. Your care plan and Today list switch too, because your care team approves them in English and Spanish. | Al guardarlo cambia el idioma de la aplicación. Tu plan de atención y tus actividades de Hoy también se muestran en ese idioma, con el texto que tu equipo aprueba en inglés y en español. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:92 / `copy.gender` | Gender | Género |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:93 / `copy.optional` | (optional) | (opcional) |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:94 / `copy.unspecified` | Not specified | Sin especificar |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:95 / `copy.dob` | Date of birth | Fecha de nacimiento |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:96 / `copy.dobLocked` | Your date of birth links your health records, so only your care team can change it. Message them if it is wrong. | Tu fecha de nacimiento vincula tus expedientes médicos, por eso solo tu equipo de atención puede cambiarla. Escríbeles si no es correcta. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:97 / `copy.timezone` | Timezone | Zona horaria |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:98 / `copy.save` | Save changes | Guardar cambios |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:99 / `copy.saving` | Saving... | Guardando... |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:100 / `copy.cancel` | Cancel | Cancelar |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:101 / `copy.saved` | Profile updated successfully. | Tu perfil se actualizó correctamente. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:103 / `copy.saveError` | We couldn’t confirm your changes were saved. Refresh to check your profile before trying again. | No pudimos confirmar que se guardaron tus cambios. Actualiza la página para revisar tu perfil antes de volver a intentarlo. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:104 / `copy.reminders` | Reminders | Recordatorios |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:105 / `copy.reminderTitle` | Medication and task reminder times | Horarios de recordatorios de medicamentos y tareas |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:107 / `copy.reminderHelp` | Choose the exact times and days you want reminders sent. | Elige las horas y los días en que deseas recibir recordatorios. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:108 / `copy.patientControlled` | Patient controlled | Tú eliges |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:109 / `copy.manageReminders` | Manage reminders | Administrar recordatorios |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:110 / `copy.connected` | Connected clinics | Clínicas vinculadas |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:111 / `copy.teams` | Care teams | Equipos de atención |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:112 / `copy.active` | Linked | Vinculado |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:113 / `copy.inactive` | Inactive | Inactivo |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:114 / `copy.transferred` | Transferred | Transferido |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:115 / `copy.unknownStatus` | Status unavailable | Estado no disponible |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:116 / `copy.teamFallback` | Care team | Equipo de atención |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:117 / `copy.noTeams` | No care teams linked yet | Aún no hay equipos de atención vinculados |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:119 / `copy.noTeamsHelp` | Add an invite code from your clinician to connect your account with a care team. | Agrega el código de invitación de tu clínico para vincular tu cuenta con un equipo de atención. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:120 / `copy.messages` | Message your care team | Enviar mensaje a tu equipo |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:122 / `copy.messageHelp` | Choose a linked clinician in Chat to send a human message. Messages are not continuously monitored. Call 911 for an emergency. | Elige un profesional vinculado en Chat para enviar un mensaje a una persona. Los mensajes no se monitorean continuamente. En una emergencia, llama al 911. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:123 / `copy.joinAnother` | Add a care team member | Agregar un miembro del equipo de atención |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:124 / `copy.connectClinic` | Add your care team | Agregar tu equipo de atención |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:125 / `copy.addTeam` | Add a care team member | Agregar un miembro del equipo de atención |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:127 / `copy.joinHelp` | Enter the invite code your clinician gave you. | Ingresa el código de invitación que te dio tu clínico. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:128 / `copy.inviteCode` | Invite code | Código de invitación |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:129 / `copy.inviteHelp` | Use the code your clinician gave you. | Usa el código que te dio tu clínico. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:130 / `copy.enterCode` | Enter an invite code to continue. | Ingresa un código de invitación para continuar. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:131 / `copy.joining` | Adding... | Agregando... |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:132 / `copy.join` | Add to my care team | Agregar a mi equipo |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:133 / `copy.joined` | Added to your care team. They are now available. | Se agregó a tu equipo de atención. Ya está disponible. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:135 / `copy.joinError` | We couldn’t confirm you were added. Refresh to check your care team before trying again. | No pudimos confirmar que se agregó. Actualiza la página para revisar tu equipo antes de volver a intentarlo. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:136 / `copy.invalidCode` | Invalid or expired invite code | El código de invitación no es válido o ya venció |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:137 / `copy.account` | Account | Cuenta |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:138 / `copy.signOutTitle` | Sign out safely | Cerrar sesión de forma segura |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:140 / `copy.signOutHelp` | Use this if you are on a shared phone or finished reviewing your care plan. | Usa esta opción si compartes tu teléfono o ya terminaste de revisar tu plan de atención. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:141 / `copy.signOut` | Sign out | Cerrar sesión |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:74 / `profileCopy.title` | Profile | Perfil |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:75 / `profileCopy.subtitle` | Manage your account and linked clinics. | Administra tu cuenta y las clínicas vinculadas. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:76 / `profileCopy.loadTitle` | Unable to load your profile | No se pudo cargar tu perfil |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:77 / `profileCopy.loadError` | We couldn’t load your account. Please try again. | No pudimos cargar tu cuenta. Inténtalo de nuevo. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:78 / `profileCopy.retry` | Try again | Intentar de nuevo |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:80 / `profileCopy.onboarding` | No active care team is linked yet. Add your care team and enter the invite code your clinician gave you. | Aún no tienes un equipo de atención activo vinculado. Agrega tu equipo e ingresa el código de invitación que te dio tu clínico. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:81 / `profileCopy.patientAccount` | Patient account | Cuenta del paciente |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:82 / `profileCopy.details` | Profile details | Detalles del perfil |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:83 / `profileCopy.personal` | Personal information | Información personal |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:84 / `profileCopy.editing` | Editing | Editando |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:85 / `profileCopy.editProfile` | Edit profile | Editar perfil |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:86 / `profileCopy.edit` | Edit | Editar |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:87 / `profileCopy.firstName` | First name | Nombre |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:88 / `profileCopy.lastName` | Last name | Apellidos |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:89 / `profileCopy.language` | Preferred language | Idioma preferido |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:91 / `profileCopy.languageHelp` | Saving this changes the app language. Your care plan and Today list switch too, because your care team approves them in English and Spanish. | Al guardarlo cambia el idioma de la aplicación. Tu plan de atención y tus actividades de Hoy también se muestran en ese idioma, con el texto que tu equipo aprueba en inglés y en español. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:92 / `profileCopy.gender` | Gender | Género |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:93 / `profileCopy.optional` | (optional) | (opcional) |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:94 / `profileCopy.unspecified` | Not specified | Sin especificar |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:95 / `profileCopy.dob` | Date of birth | Fecha de nacimiento |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:96 / `profileCopy.dobLocked` | Your date of birth links your health records, so only your care team can change it. Message them if it is wrong. | Tu fecha de nacimiento vincula tus expedientes médicos, por eso solo tu equipo de atención puede cambiarla. Escríbeles si no es correcta. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:97 / `profileCopy.timezone` | Timezone | Zona horaria |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:98 / `profileCopy.save` | Save changes | Guardar cambios |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:99 / `profileCopy.saving` | Saving... | Guardando... |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:100 / `profileCopy.cancel` | Cancel | Cancelar |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:101 / `profileCopy.saved` | Profile updated successfully. | Tu perfil se actualizó correctamente. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:103 / `profileCopy.saveError` | We couldn’t confirm your changes were saved. Refresh to check your profile before trying again. | No pudimos confirmar que se guardaron tus cambios. Actualiza la página para revisar tu perfil antes de volver a intentarlo. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:104 / `profileCopy.reminders` | Reminders | Recordatorios |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:105 / `profileCopy.reminderTitle` | Medication and task reminder times | Horarios de recordatorios de medicamentos y tareas |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:107 / `profileCopy.reminderHelp` | Choose the exact times and days you want reminders sent. | Elige las horas y los días en que deseas recibir recordatorios. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:108 / `profileCopy.patientControlled` | Patient controlled | Tú eliges |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:109 / `profileCopy.manageReminders` | Manage reminders | Administrar recordatorios |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:110 / `profileCopy.connected` | Connected clinics | Clínicas vinculadas |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:111 / `profileCopy.teams` | Care teams | Equipos de atención |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:112 / `profileCopy.active` | Linked | Vinculado |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:113 / `profileCopy.inactive` | Inactive | Inactivo |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:114 / `profileCopy.transferred` | Transferred | Transferido |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:115 / `profileCopy.unknownStatus` | Status unavailable | Estado no disponible |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:116 / `profileCopy.teamFallback` | Care team | Equipo de atención |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:117 / `profileCopy.noTeams` | No care teams linked yet | Aún no hay equipos de atención vinculados |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:119 / `profileCopy.noTeamsHelp` | Add an invite code from your clinician to connect your account with a care team. | Agrega el código de invitación de tu clínico para vincular tu cuenta con un equipo de atención. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:120 / `profileCopy.messages` | Message your care team | Enviar mensaje a tu equipo |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:122 / `profileCopy.messageHelp` | Choose a linked clinician in Chat to send a human message. Messages are not continuously monitored. Call 911 for an emergency. | Elige un profesional vinculado en Chat para enviar un mensaje a una persona. Los mensajes no se monitorean continuamente. En una emergencia, llama al 911. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:123 / `profileCopy.joinAnother` | Add a care team member | Agregar un miembro del equipo de atención |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:124 / `profileCopy.connectClinic` | Add your care team | Agregar tu equipo de atención |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:125 / `profileCopy.addTeam` | Add a care team member | Agregar un miembro del equipo de atención |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:127 / `profileCopy.joinHelp` | Enter the invite code your clinician gave you. | Ingresa el código de invitación que te dio tu clínico. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:128 / `profileCopy.inviteCode` | Invite code | Código de invitación |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:129 / `profileCopy.inviteHelp` | Use the code your clinician gave you. | Usa el código que te dio tu clínico. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:130 / `profileCopy.enterCode` | Enter an invite code to continue. | Ingresa un código de invitación para continuar. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:131 / `profileCopy.joining` | Adding... | Agregando... |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:132 / `profileCopy.join` | Add to my care team | Agregar a mi equipo |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:133 / `profileCopy.joined` | Added to your care team. They are now available. | Se agregó a tu equipo de atención. Ya está disponible. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:135 / `profileCopy.joinError` | We couldn’t confirm you were added. Refresh to check your care team before trying again. | No pudimos confirmar que se agregó. Actualiza la página para revisar tu equipo antes de volver a intentarlo. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:136 / `profileCopy.invalidCode` | Invalid or expired invite code | El código de invitación no es válido o ya venció |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:137 / `profileCopy.account` | Account | Cuenta |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:138 / `profileCopy.signOutTitle` | Sign out safely | Cerrar sesión de forma segura |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:140 / `profileCopy.signOutHelp` | Use this if you are on a shared phone or finished reviewing your care plan. | Usa esta opción si compartes tu teléfono o ya terminaste de revisar tu plan de atención. |
| apps/patient-portal/src/app/(app)/profile/profile-copy.ts:141 / `profileCopy.signOut` | Sign out | Cerrar sesión |
| apps/patient-portal/src/components/features/nora-conversations.tsx:25 / `locales.heading` | Past conversations with Nora | Conversaciones anteriores con Nora |
| apps/patient-portal/src/components/features/nora-conversations.tsx:26 / `locales.today` | Today | Hoy |
| apps/patient-portal/src/components/features/nora-conversations.tsx:27 / `locales.untitled` | Conversation | Conversación |
| apps/patient-portal/src/components/features/nora-conversations.tsx:28 / `locales.loadError` | Past conversations could not be loaded. | No se pudieron cargar las conversaciones anteriores. |
| apps/patient-portal/src/components/features/nora-conversations.tsx:29 / `locales.dayTitle` | Conversation from | Conversación del |
| apps/patient-portal/src/components/features/nora-conversations.tsx:30 / `locales.todayTitle` | Today's conversation | Conversación de hoy |
| apps/patient-portal/src/components/features/nora-conversations.tsx:32 / `locales.unfinished` | Reply unfinished | Respuesta incompleta |
| apps/patient-portal/src/components/features/nora-conversations.tsx:33 / `locales.replying` | Nora is replying… | Nora está respondiendo… |
| packages/shared/src/utils/care-conversations.ts:179 / `getConversationCopy.recipient` | Choose recipient | Elegir destinatario |
| packages/shared/src/utils/care-conversations.ts:179 / `getConversationCopy.choose` | Select a person | Selecciona una persona |
| packages/shared/src/utils/care-conversations.ts:179 / `getConversationCopy.open` | Open conversation | Abrir conversación |
| packages/shared/src/utils/care-conversations.ts:180 / `getConversationCopy.threads` | Conversations | Conversaciones |
| packages/shared/src/utils/care-conversations.ts:180 / `getConversationCopy.empty` | No conversations yet. | Todavía no hay conversaciones. |
| packages/shared/src/utils/care-conversations.ts:180 / `getConversationCopy.noRecipients` | No linked recipients available. | No hay destinatarios vinculados disponibles. |
| packages/shared/src/utils/care-conversations.ts:181 / `getConversationCopy.select` | Choose a conversation or a recipient to begin. | Elige una conversación o un destinatario para comenzar. |
| packages/shared/src/utils/care-conversations.ts:181 / `getConversationCopy.loading` | Loading… | Cargando… |
| packages/shared/src/utils/care-conversations.ts:181 / `getConversationCopy.refresh` | Refresh | Actualizar |
| packages/shared/src/utils/care-conversations.ts:182 / `getConversationCopy.retry` | Retry | Reintentar |
| packages/shared/src/utils/care-conversations.ts:182 / `getConversationCopy.older` | Load older messages | Cargar mensajes anteriores |
| packages/shared/src/utils/care-conversations.ts:182 / `getConversationCopy.message` | Message | Mensaje |
| packages/shared/src/utils/care-conversations.ts:182 / `getConversationCopy.send` | Send message | Enviar mensaje |
| packages/shared/src/utils/care-conversations.ts:182 / `getConversationCopy.sending` | Sending… | Enviando… |
| packages/shared/src/utils/care-conversations.ts:183 / `getConversationCopy.uncertain` | Send could not be confirmed. Your message is preserved; retry the same send to avoid duplicates. | No se pudo confirmar el envío. Tu mensaje se conserva; reintenta el mismo envío para evitar duplicados. |
| packages/shared/src/utils/care-conversations.ts:184 / `getConversationCopy.loadError` | Could not load the conversation. Please try again. | No se pudo cargar la conversación. Intenta de nuevo. |
| packages/shared/src/utils/care-conversations.ts:184 / `getConversationCopy.denied` | This conversation is unavailable. Refresh conversations. | Esta conversación no está disponible. Actualiza las conversaciones. |
| packages/shared/src/utils/care-conversations.ts:185 / `getConversationCopy.readError` | Could not update the unread count. Try refreshing. | No se pudo actualizar el contador de mensajes no leídos. Intenta actualizar. |
| packages/shared/src/utils/care-conversations.ts:186 / `getConversationCopy.savedRefreshError` | Message saved. Could not refresh the conversation; refresh to see recent messages. | Mensaje guardado. No se pudo actualizar la conversación; actualiza para ver los mensajes recientes. |
| packages/shared/src/utils/care-conversations.ts:187 / `getConversationCopy.noMessages` | No messages yet. | Todavía no hay mensajes. |
| packages/shared/src/utils/care-conversations.ts:187 / `getConversationCopy.unread` | unread | sin leer |
| packages/shared/src/utils/care-conversations.ts:187 / `getConversationCopy.notice` | Messages are not continuously monitored. For an emergency, call 911. | Estos mensajes no se supervisan continuamente. Para una emergencia, llama al 911. |
| packages/shared/src/utils/care-conversations.ts:188 / `getConversationCopy.locked` | Retry the pending send before editing this message. | Reintenta el envío pendiente antes de editar este mensaje. |
| packages/shared/src/utils/care-conversations.ts:189 / `getConversationCopy.mismatch` | The retry was rejected because it does not match the original send. The previous message may already exist. Refresh and review the history before preparing a new send. | El reintento fue rechazado porque no coincide con el envío original. El mensaje anterior puede ya existir. Actualiza y revisa el historial antes de preparar otro envío. |
| packages/shared/src/utils/care-conversations.ts:190 / `getConversationCopy.invalid` | The message was rejected. Your text is preserved; review or edit it before sending again. | El mensaje fue rechazado. Tu texto se conserva; revísalo o edítalo antes de volver a enviarlo. |
| packages/shared/src/utils/care-conversations.ts:191 / `getConversationCopy.activityUnavailable` | The attached activity is no longer available. Your text is preserved. Remove it or reload activities before sending. | La actividad adjunta ya no está disponible. Conservamos tu texto. Quita la actividad o vuelve a cargar las actividades antes de enviar. |
| packages/shared/src/utils/care-conversations.ts:192 / `getConversationCopy.prepareNew` | Prepare a new send | Preparar un nuevo envío |
| packages/shared/src/utils/care-conversations.ts:192 / `getConversationCopy.confirmNew` | Confirm: prepare a new send | Confirmar: preparar un nuevo envío |
| packages/shared/src/utils/care-conversations.ts:192 / `getConversationCopy.cancel` | Cancel | Cancelar |
| packages/shared/src/utils/care-conversations.ts:193 / `getConversationCopy.confirmWarning` | The previous message may already exist. Preparing a new send permits another message and could duplicate it. This action does not send it. | El mensaje anterior puede ya existir. Preparar un nuevo envío permite crear otro mensaje y podría duplicarlo. Esta acción no lo envía. |
| packages/shared/src/utils/care-conversations.ts:194 / `getConversationCopy.translatedFromEnglish` | Translated from English | Traducido del inglés |
| packages/shared/src/utils/care-conversations.ts:194 / `getConversationCopy.translatedFromSpanish` | Translated from Spanish | Traducido del español |
| packages/shared/src/utils/care-conversations.ts:195 / `getConversationCopy.showOriginal` | Show original | Ver original |
| packages/shared/src/utils/care-conversations.ts:195 / `getConversationCopy.showTranslation` | Show translation | Ver traducción |
| packages/shared/src/utils/care-conversations.ts:195 / `getConversationCopy.translationUncertain` | numbers may differ | las cifras pueden diferir |
| packages/shared/src/utils/care-conversations.ts:196 / `getConversationCopy.translationUnavailable` | Automatic translation unavailable for this message | Traducción automática no disponible para este mensaje |
| packages/shared/src/utils/care-conversations.ts:197 / `getConversationCopy.activityAsk` | Ask about a plan activity | Preguntar sobre una actividad del plan |
| packages/shared/src/utils/care-conversations.ts:198 / `getConversationCopy.activityAttachedButton` | (title: string) =&gt; `Attached activity: ${title}` | (title: string) =&gt; `Actividad adjunta: ${title}` |
| packages/shared/src/utils/care-conversations.ts:199 / `getConversationCopy.activityLabel` | Activity you are asking about (optional) | Actividad sobre la que preguntas (opcional) |
| packages/shared/src/utils/care-conversations.ts:200 / `getConversationCopy.activityLoading` | Loading activities… | Cargando actividades… |
| packages/shared/src/utils/care-conversations.ts:201 / `getConversationCopy.activityNone` | No activity attached | Sin actividad adjunta |
| packages/shared/src/utils/care-conversations.ts:202 / `getConversationCopy.activityPreviouslyAttached` | Previously attached activity | Actividad adjunta anteriormente |
| packages/shared/src/utils/care-conversations.ts:203 / `getConversationCopy.activityLoadError` | Activities could not be loaded. | No se pudieron cargar las actividades. |
| packages/shared/src/utils/care-conversations.ts:204 / `getConversationCopy.activityRetry` | Retry loading activities | Reintentar actividades |
| packages/shared/src/utils/care-conversations.ts:205 / `getConversationCopy.activityExplanation` | Your message does not change the plan or reminders. Your care team must review and approve any change. | Tu mensaje no cambia el plan ni los recordatorios. Tu equipo debe revisar y aprobar cualquier cambio. |
| packages/shared/src/utils/care-conversations.ts:206 / `getConversationCopy.activityLocked` | The activity cannot be changed while this message is being confirmed or retried. | La actividad no se puede cambiar mientras se confirma o reintenta este mensaje. |
| packages/shared/src/utils/care-conversations.ts:207 / `getConversationCopy.activityAttached` | Attached plan activity | Actividad del plan adjunta |
| packages/shared/src/utils/care-conversations.ts:208 / `getConversationCopy.activityNotCurrent` | This activity is no longer part of the current plan. | Esta actividad ya no pertenece al plan actual. |
| packages/shared/src/utils/care-conversations.ts:210 / `getConversationCopy.translating` | Translating… | Traduciendo… |
| packages/shared/src/utils/care-conversations.ts:212 / `getConversationCopy.aboutTranslation` | About this translation | Acerca de esta traducción |
| packages/shared/src/utils/care-conversations.ts:213 / `getConversationCopy.aboutTranslationTitle` | This translation is automatic | Esta traducción es automática |
| packages/shared/src/utils/care-conversations.ts:214 / `getConversationCopy.translationMayErr` | A computer made it, not a person, and it may contain errors. | La hizo una computadora, no una persona, y puede tener errores. |
| packages/shared/src/utils/care-conversations.ts:215 / `getConversationCopy.translationModel` | (model: string) =&gt; `It was made by the ${model} model.` | (model: string) =&gt; `La hizo el modelo ${model}.` |
| packages/shared/src/utils/care-conversations.ts:216 / `getConversationCopy.translationModelUnknown` | Which model made it was not recorded. | No se registró qué modelo la hizo. |
| packages/shared/src/utils/care-conversations.ts:217 / `getConversationCopy.translationOriginalIsRecord` | The original message is the one that counts. Your care team reads the original, not the translation. | El mensaje original es el que cuenta. Tu equipo de atención lee el original, no la traducción. |
| packages/shared/src/utils/care-conversations.ts:218 / `getConversationCopy.translationGuards` | We check that numbers, doses and medication names are the same in both languages. If something does not match, we do not show the translation. | Revisamos que los números, las dosis y los nombres de los medicamentos sean iguales en los dos idiomas. Si algo no coincide, no mostramos la traducción. |
| packages/shared/src/utils/care-conversations.ts:219 / `getConversationCopy.translationAsk` | If anything is unclear, ask your care team. | Si algo no te queda claro, pregúntale a tu equipo de atención. |
| packages/shared/src/utils/care-conversations.ts:220 / `getConversationCopy.close` | Close | Cerrar |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.legacy_update.0` | Earlier notification | Notificación anterior |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.legacy_update.1` | From the previous inbox; not a new task. | De tu buzón anterior; no es una tarea nueva. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.message_received.0` | New care-team message | Nuevo mensaje del equipo de atención |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.message_received.1` | Open the conversation to read it. | Abre la conversación para leerlo. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.appointment_offered.0` | Appointment offered | Propuesta de cita |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.appointment_offered.1` | Choose a time in Visits. | Elige un horario en Citas. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.appointment_changed.0` | Appointment updated | Cita actualizada |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.appointment_changed.1` | See the current time in Visits. | Consulta el horario actual en Citas. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.appointment_cancelled.0` | Appointment cancelled | Cita cancelada |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.appointment_cancelled.1` | Your clinician cancelled this visit. See the reason in Visits. | Tu profesional clínico canceló esta cita. Consulta el motivo en Citas. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.appointment_response.0` | Patient responded to an appointment | El paciente respondió a una cita |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.appointment_response.1` | Review the saved patient response. | Revisa la respuesta guardada del paciente. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.appointment_reminder.0` | Appointment reminder | Recordatorio de cita |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.appointment_reminder.1` | Time and place are in Visits. | El horario y el lugar están en Citas. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.care_plan_published.0` | Your care plan was updated | Tu plan de cuidado se actualizó |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.care_plan_published.1` | Your care team approved changes. See Today. | Tu equipo de atención aprobó cambios. Consulta Hoy. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.care_plan_draft.0` | Care-plan draft ready for review | Borrador del plan listo para revisión |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.care_plan_draft.1` | This draft is not published. Review sources, wording and blockers. | Este borrador no está publicado. Revisa las fuentes, el texto y los bloqueos. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.document_review.0` | Patient document awaiting review | Documento del paciente pendiente de revisión |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.document_review.1` | Parsing and clinical review are separate. Open the exact document. | El procesamiento y la revisión clínica son pasos distintos. Abre el documento correspondiente. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.document_processed.0` | Document processing completed | Documento procesado |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.document_processed.1` | See it in Records. | Consúltalo en Registros. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.document_failed.0` | Document needs attention | El documento necesita atención |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.document_failed.1` | Processing didn't finish. Open it for next steps. | El procesamiento no terminó. Ábrelo para ver los siguientes pasos. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.document_reviewed.0` | Document review updated | Revisión del documento actualizada |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.document_reviewed.1` | Your care team reviewed it. See Records. | Tu equipo de atención lo revisó. Consulta Registros. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.barrier_reported.0` | Care-plan barrier reported | Dificultad con el plan de atención reportada |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.barrier_reported.1` | A patient reported difficulty with an activity. This is not a confirmed adverse drug reaction. | Un paciente reportó una dificultad con una actividad. Esto no confirma una reacción adversa a un medicamento. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.adr_review.0` | Medication-safety review needed | Se necesita una revisión de seguridad de medicamentos |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.adr_review.1` | A candidate finding needs clinician review; it is not a confirmed diagnosis. | Un hallazgo candidato necesita revisión clínica; no es un diagnóstico confirmado. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.adr_information_requested.0` | Your care team requested information | Tu equipo de atención solicita información |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.adr_information_requested.1` | Answer a few questions in the app about a symptom you already reported. Describe only what already happened. | Responde en la app unas preguntas sobre un síntoma que ya reportaste. Describe solo lo que ya pasó. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.adr_information_answered.0` | Patient answered medication-safety follow-up | El paciente respondió al seguimiento de seguridad de medicamentos |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.adr_information_answered.1` | A patient sent answers to follow-up questions. Review the updated evidence; this is not a clinical decision. | Un paciente envió respuestas a preguntas de seguimiento. Revisa la evidencia actualizada; esto no es una decisión clínica. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.symptom_report_reviewed.0` | Your care team reviewed your symptom report | Tu equipo de atención revisó tu reporte de síntomas |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.symptom_report_reviewed.1` | See your symptom report. | Consulta tu reporte de síntomas. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.medication_confirmation_asked.0` | Your care team asked about one of your medicines | Tu equipo de atención te preguntó sobre uno de tus medicamentos |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.medication_confirmation_asked.1` | Open Today to answer. Your answer does not change any medicine or reminder. | Abre Hoy para responder. Tu respuesta no cambia ningún medicamento ni recordatorio. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.critical_result.0` | Critical test result reported | Resultado crítico de laboratorio reportado |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.critical_result.1` | A patient's document reports a result the laboratory marked critical. Open the document to review it. | Un documento del paciente informa un resultado que el laboratorio marcó como crítico. Ábrelo para revisarlo. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.care_plan_review.0` | Care-team work item | Tarea del equipo de atención |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.care_plan_review.1` | A care-plan item needs your care team. Open the patient to see it. | Un elemento del plan de atención requiere la atención de tu equipo. Abre el expediente del paciente para verlo. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.handoff_shared.0` | A colleague shared a handoff summary | Un colega compartió un resumen de entrega |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.handoff_shared.1` | Open the approved summary. It is read-only; sharing does not give access to the record. | Abre el resumen aprobado. Es de solo lectura; compartirlo no da acceso al expediente. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.safety_flag.0` | Patient safety flag needs review | Aviso de seguridad del paciente pendiente de revisión |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.safety_flag.1` | An automated flag was saved. Review the original conversation; this is not a clinical decision. | Se guardó un aviso automático. Revisa la conversación original; esto no es una decisión clínica. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.med_reminder.0` | Medication reminder | Recordatorio de medicamento |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.med_reminder.1` | It's on your Today list. | Está en tu lista de Hoy. |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.obligation_reminder.0` | Care-plan reminder | Recordatorio del plan de cuidado |
| backend/src/app/services/notification_centre_presentation.py:11 / `_COPY.obligation_reminder.1` | It's on your Today list. | Está en tu lista de Hoy. |
| backend/src/app/services/notification_centre_presentation.py:178 / `_QUESTION_WORDING.event_after_drug.0` | Whether the symptom started after you began this medicine | Si el síntoma empezó después de que comenzaste a tomar este medicamento |
| backend/src/app/services/notification_centre_presentation.py:178 / `_QUESTION_WORDING.improved_on_dechallenge.0` | Whether the symptom got better after this medicine was stopped or paused | Si el síntoma mejoró después de que se suspendió o pausó este medicamento |
| backend/src/app/services/notification_centre_presentation.py:178 / `_QUESTION_WORDING.reappeared_on_rechallenge.0` | Whether the symptom came back after restarting this medicine | Si el síntoma volvió después de reiniciar este medicamento |
| backend/src/app/services/notification_centre_presentation.py:178 / `_QUESTION_WORDING.dose_response.0` | Whether the symptom changed after a dose change your clinician directed | Si el síntoma cambió después de un cambio de dosis indicado por tu profesional de salud |
| backend/src/app/services/notification_centre_presentation.py:178 / `_QUESTION_WORDING.similar_previous_reaction.0` | Whether you have had a similar reaction to this medicine before | Si has tenido antes una reacción similar a este medicamento |
| backend/src/app/services/symptom_report_presenter.py:21 / `_LABELS.description` | What happened | Qué pasó |
| backend/src/app/services/symptom_report_presenter.py:21 / `_LABELS.location` | Where | Dónde |
| backend/src/app/services/symptom_report_presenter.py:21 / `_LABELS.onset` | When it started | Cuándo empezó |
| backend/src/app/services/symptom_report_presenter.py:21 / `_LABELS.duration` | How long | Cuánto tiempo |
| backend/src/app/services/symptom_report_presenter.py:21 / `_LABELS.course` | How it has changed | Cómo ha cambiado |
| backend/src/app/services/symptom_report_presenter.py:21 / `_LABELS.severity` | Severity (0 to 10) | Intensidad (0 a 10) |
| backend/src/app/services/symptom_report_presenter.py:21 / `_LABELS.associated` | Other symptoms | Otros síntomas |
| backend/src/app/services/symptom_report_presenter.py:21 / `_LABELS.red_flags` | Warning signs | Señales de alerta |
| backend/src/app/services/symptom_report_presenter.py:21 / `_LABELS.product` | Product involved | Producto involucrado |
| backend/src/app/services/symptom_report_presenter.py:21 / `_LABELS.concomitant` | Other products | Otros productos |
| backend/src/app/services/symptom_report_presenter.py:21 / `_LABELS.history` | Related history | Antecedentes relacionados |
| backend/src/app/services/symptom_report_presenter.py:21 / `_LABELS.outcome` | Outcome so far | Resultado hasta ahora |
| backend/src/app/services/symptom_report_presenter.py:51 / `_PRODUCT_LABELS.concern` | Product concern | Preocupación por un producto |
| backend/src/app/services/symptom_report_presenter.py:51 / `_PRODUCT_LABELS.name` | Product | Producto |
| backend/src/app/services/symptom_report_presenter.py:51 / `_PRODUCT_LABELS.strength` | Strength | Concentración |
| backend/src/app/services/symptom_report_presenter.py:51 / `_PRODUCT_LABELS.dose` | Dose | Dosis |
| backend/src/app/services/symptom_report_presenter.py:51 / `_PRODUCT_LABELS.route` | Route | Vía |
| backend/src/app/services/symptom_report_presenter.py:51 / `_PRODUCT_LABELS.indication` | Reason for use | Motivo de uso |
| backend/src/app/services/symptom_report_presenter.py:51 / `_PRODUCT_LABELS.start` | Start | Inicio |
| backend/src/app/services/symptom_report_presenter.py:51 / `_PRODUCT_LABELS.stop` | Stop | Suspensión |
| backend/src/app/services/symptom_report_presenter.py:51 / `_PRODUCT_LABELS.change` | Change | Cambio |
| backend/src/app/services/symptom_report_presenter.py:75 / `_UNRESOLVED.unknown` | I don’t know | No sé |
| backend/src/app/services/symptom_report_presenter.py:75 / `_UNRESOLVED.declined` | Prefer not to answer | Prefiero no responder |
| backend/src/app/services/symptom_report_presenter.py:79 / `_YES_NO.0` | Yes | Sí |
| backend/src/app/services/symptom_report_presenter.py:79 / `_YES_NO.1` | No | No |
| backend/src/app/services/appointment_calendar.py:12 / `_COPY.0` | MediAgent appointment | Cita de MediAgent |
| backend/src/app/services/appointment_calendar.py:12 / `_COPY.1` | This is a one-time calendar copy. Changes and cancellations do not sync. Check MediAgent for the latest appointment details. | Esta es una copia única para tu calendario. Los cambios y las cancelaciones no se sincronizan. Consulta MediAgent para ver los datos actuales de la cita. |
| backend/src/app/services/appointment_calendar.py:12 / `_COPY.2` | Clinic | Clínica |
| backend/src/app/services/email_service.py:28 / `_COPY.message_received.0` | New care-team messages | Nuevos mensajes del equipo de atención |
| backend/src/app/services/email_service.py:28 / `_COPY.appointment_offered.0` | Appointment choices available | Horarios de cita disponibles |
| backend/src/app/services/email_service.py:28 / `_COPY.appointment_changed.0` | Appointment updated | Cita actualizada |
| backend/src/app/services/email_service.py:28 / `_COPY.appointment_cancelled.0` | Appointment cancelled | Cita cancelada |
| backend/src/app/services/email_service.py:28 / `_COPY.appointment_response.0` | Appointment response received | Respuesta a la cita recibida |
| backend/src/app/services/email_service.py:28 / `_COPY.care_plan_published.0` | Your care plan was updated | Tu plan de cuidado se actualizó |
| backend/src/app/services/email_service.py:28 / `_COPY.document_failed.0` | A document needs your attention | Un documento necesita tu atención |
| backend/src/app/services/email_service.py:28 / `_COPY.adr_information_requested.0` | Your care team requested information | Tu equipo de atención solicita información |
| backend/src/app/services/email_service.py:28 / `_COPY.document_review.0` | Review work available | Revisión pendiente |
| backend/src/app/services/email_service.py:28 / `_COPY.care_plan_draft.0` | Review work available | Revisión pendiente |
| backend/src/app/services/email_service.py:28 / `_COPY.critical_result.0` | Urgent review work available | Revisión urgente pendiente |

## Scope outside static interface copy

Stored care-plan wording, historical human messages, question-library content and
generated clinical translations require their own source-linked review. They are
not replaced by this interface pack. Existing clinical safety copy is unchanged.
The linked [LOC-001 contract](../.agent/specs/loc-001-bilingual-approved-wording.md)
owns approval semantics; [the task board](../.agent/TASKS.md) owns current status.
