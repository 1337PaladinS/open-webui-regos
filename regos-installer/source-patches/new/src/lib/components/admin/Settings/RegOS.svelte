<script>
	import { onMount, getContext } from 'svelte';
	import { toast } from 'svelte-sonner';

	import Switch from '$lib/components/common/Switch.svelte';
	import Textarea from '$lib/components/common/Textarea.svelte';
	import { getRegosConfig, updateRegosConfig } from '$lib/apis/configs';

	const i18n = getContext('i18n');

	export let saveHandler = () => {};

	// Disclaimer settings
	let disclaimerEnabled = true;
	let disclaimerTitle = 'Welcome to RegOS Compliance Copilot';
	let disclaimerBody = '';
	let disclaimerAcceptLabel = 'I Understand & Accept';

	// Guest access settings
	let guestEnabled = true;
	let guestMessageLimit = 10;
	let guestGenerationLimit = 50;
	let guestSessionTtl = 10800;
	let guestShowButton = true;

	// Confidence display settings
	let confidenceEnabled = true;
	let confidenceStyle = 'emoji_blockquote';
	let confidenceHighThreshold = 70;
	let confidenceMediumThreshold = 45;

	// Markdown preview toggle
	let showPreview = false;

	const updateHandler = async () => {
		try {
			const res = await updateRegosConfig(localStorage.token, {
				disclaimer: {
					enabled: disclaimerEnabled,
					title: disclaimerTitle,
					body: disclaimerBody,
					accept_label: disclaimerAcceptLabel
				},
				guest: {
					enabled: guestEnabled,
					message_limit: guestMessageLimit,
					generation_limit: guestGenerationLimit,
					session_ttl: guestSessionTtl,
					show_button: guestShowButton
				},
				confidence: {
					enabled: confidenceEnabled,
					style: confidenceStyle,
					high_threshold: confidenceHighThreshold,
					medium_threshold: confidenceMediumThreshold
				}
			});

			if (res) {
				toast.success($i18n.t('RegOS settings saved'));
				saveHandler();
			} else {
				toast.error($i18n.t('Failed to update RegOS settings'));
			}
		} catch (err) {
			toast.error(`${err}`);
		}
	};

	onMount(async () => {
		try {
			const res = await getRegosConfig(localStorage.token);
			if (res) {
				disclaimerEnabled = res.disclaimer.enabled;
				disclaimerTitle = res.disclaimer.title;
				disclaimerBody = res.disclaimer.body;
				disclaimerAcceptLabel = res.disclaimer.accept_label;

				guestEnabled = res.guest.enabled;
				guestMessageLimit = res.guest.message_limit;
				guestGenerationLimit = res.guest.generation_limit;
				guestSessionTtl = res.guest.session_ttl;
				guestShowButton = res.guest.show_button;

				confidenceEnabled = res.confidence.enabled;
				confidenceStyle = res.confidence.style;
				confidenceHighThreshold = res.confidence.high_threshold;
				confidenceMediumThreshold = res.confidence.medium_threshold;
			}
		} catch (err) {
			console.error('Failed to load RegOS config:', err);
		}
	});

	$: ttlHours = Math.round((guestSessionTtl / 3600) * 10) / 10;
</script>

<form
	class="flex flex-col h-full justify-between text-sm"
	on:submit|preventDefault={() => {
		updateHandler();
	}}
>
	<div class="overflow-y-scroll scrollbar-hidden h-full pr-1.5">
		<!-- ═══════════════════════════════════════════ -->
		<!-- SECTION 1: Onboarding Disclaimer           -->
		<!-- ═══════════════════════════════════════════ -->
		<div class="mb-6">
			<div class="flex items-center gap-2 mb-3">
				<div class="text-base font-semibold">{$i18n.t('Onboarding Disclaimer')}</div>
			</div>

			<div class="mb-3 flex w-full items-center justify-between">
				<div class="self-center text-xs font-medium">
					{$i18n.t('Enable Disclaimer Modal')}
				</div>
				<Switch bind:state={disclaimerEnabled} />
			</div>

			{#if disclaimerEnabled}
				<div class="mb-3">
					<div class="mb-1 text-xs font-medium">{$i18n.t('Modal Title')}</div>
					<input
						class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-none"
						type="text"
						bind:value={disclaimerTitle}
						placeholder="Welcome to RegOS Compliance Copilot"
					/>
				</div>

				<div class="mb-3">
					<div class="mb-1 flex items-center justify-between">
						<div class="text-xs font-medium">{$i18n.t('Disclaimer Body (Markdown)')}</div>
						<button
							type="button"
							class="text-xs text-blue-500 hover:text-blue-600 dark:text-blue-400"
							on:click={() => { showPreview = !showPreview; }}
						>
							{showPreview ? $i18n.t('Edit') : $i18n.t('Preview')}
						</button>
					</div>

					{#if showPreview}
						<div class="w-full rounded-lg py-3 px-4 text-sm bg-gray-50 dark:bg-gray-850 dark:text-gray-300 prose dark:prose-invert prose-sm max-w-none min-h-[200px] overflow-y-auto">
							{@html disclaimerBody
								.replace(/^### (.*$)/gm, '<h3>$1</h3>')
								.replace(/^## (.*$)/gm, '<h2>$1</h2>')
								.replace(/^# (.*$)/gm, '<h1>$1</h1>')
								.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
								.replace(/\*(.*?)\*/g, '<em>$1</em>')
								.replace(/^- (.*$)/gm, '<li>$1</li>')
								.replace(/(<li>.*<\/li>)/gms, '<ul>$1</ul>')
								.replace(/\n\n/g, '<br/><br/>')
								.replace(/\n/g, '<br/>')
							}
						</div>
					{:else}
						<textarea
							class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-none font-mono resize-y"
							rows="10"
							bind:value={disclaimerBody}
							placeholder="Enter disclaimer content in Markdown format...&#10;&#10;RegOS analyses are **AI-assisted regulatory reviews** based on Miami-Dade County Chapter 24..."
						/>
					{/if}
				</div>

				<div class="mb-3">
					<div class="mb-1 text-xs font-medium">{$i18n.t('Accept Button Label')}</div>
					<input
						class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-none"
						type="text"
						bind:value={disclaimerAcceptLabel}
						placeholder="I Understand & Accept"
					/>
				</div>
			{/if}
		</div>

		<hr class="border-gray-100 dark:border-gray-850 mb-6" />

		<!-- ═══════════════════════════════════════════ -->
		<!-- SECTION 2: Guest Access                    -->
		<!-- ═══════════════════════════════════════════ -->
		<div class="mb-6">
			<div class="flex items-center gap-2 mb-3">
				<div class="text-base font-semibold">{$i18n.t('Guest Access')}</div>
			</div>

			<div class="mb-3 flex w-full items-center justify-between">
				<div class="self-center text-xs font-medium">
					{$i18n.t('Enable Guest Mode')}
				</div>
				<Switch bind:state={guestEnabled} />
			</div>

			{#if guestEnabled}
				<div class="mb-3 flex w-full items-center justify-between">
					<div class="self-center text-xs font-medium">
						{$i18n.t('Show "Continue as Guest" Button')}
					</div>
					<Switch bind:state={guestShowButton} />
				</div>

				<div class="mb-3">
					<div class="mb-1 text-xs font-medium">
						{$i18n.t('Message Limit per Session')}
					</div>
					<input
						class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-none"
						type="number"
						min="1"
						max="100"
						bind:value={guestMessageLimit}
					/>
					<div class="mt-1 text-xs text-gray-500">{$i18n.t('Maximum number of chats a guest can create before being prompted to sign up.')}</div>
				</div>

				<div class="mb-3">
					<div class="mb-1 text-xs font-medium">
						{$i18n.t('Generation Limit per Session')}
					</div>
					<input
						class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-none"
						type="number"
						min="1"
						max="500"
						bind:value={guestGenerationLimit}
					/>
					<div class="mt-1 text-xs text-gray-500">{$i18n.t('Maximum number of AI responses a guest can receive across all chats. Set to 0 for unlimited.')}</div>
				</div>

				<div class="mb-3">
					<div class="mb-1 text-xs font-medium">
						{$i18n.t('Session TTL (seconds)')}
					</div>
					<input
						class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-none"
						type="number"
						min="300"
						max="86400"
						step="300"
						bind:value={guestSessionTtl}
					/>
					<div class="mt-1 text-xs text-gray-500">
						{$i18n.t('Guest sessions expire after this duration.')} ({ttlHours} {$i18n.t('hours')})
					</div>
				</div>
			{/if}
		</div>

		<hr class="border-gray-100 dark:border-gray-850 mb-6" />

		<!-- ═══════════════════════════════════════════ -->
		<!-- SECTION 3: Confidence Display              -->
		<!-- ═══════════════════════════════════════════ -->
		<div class="mb-6">
			<div class="flex items-center gap-2 mb-3">
				<div class="text-base font-semibold">{$i18n.t('Confidence Display')}</div>
			</div>

			<div class="mb-3 flex w-full items-center justify-between">
				<div class="self-center text-xs font-medium">
					{$i18n.t('Show Confidence Banner')}
				</div>
				<Switch bind:state={confidenceEnabled} />
			</div>

			{#if confidenceEnabled}
				<div class="mb-3">
					<div class="mb-1 text-xs font-medium">{$i18n.t('Display Style')}</div>
					<select
						class="w-full rounded-lg py-2 px-4 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-none"
						bind:value={confidenceStyle}
					>
						<option value="emoji_blockquote">Emoji Blockquote (Recommended)</option>
						<option value="plain_text">Plain Text</option>
						<option value="hidden">Hidden (Data Only)</option>
					</select>
					<div class="mt-1 text-xs text-gray-500">{$i18n.t('"Hidden" still records confidence data for audit but shows no banner.')}</div>
				</div>

				<div class="mb-3">
					<div class="mb-1 text-xs font-medium">
						{$i18n.t('HIGH Confidence Threshold')} ({confidenceHighThreshold}%)
					</div>
					<input
						class="w-full"
						type="range"
						min="50"
						max="95"
						step="5"
						bind:value={confidenceHighThreshold}
					/>
					<div class="flex justify-between text-xs text-gray-400">
						<span>50%</span>
						<span>95%</span>
					</div>
				</div>

				<div class="mb-3">
					<div class="mb-1 text-xs font-medium">
						{$i18n.t('MEDIUM Confidence Threshold')} ({confidenceMediumThreshold}%)
					</div>
					<input
						class="w-full"
						type="range"
						min="20"
						max="{confidenceHighThreshold - 5}"
						step="5"
						bind:value={confidenceMediumThreshold}
					/>
					<div class="flex justify-between text-xs text-gray-400">
						<span>20%</span>
						<span>{confidenceHighThreshold - 5}%</span>
					</div>
				</div>

				<div class="rounded-lg bg-gray-50 dark:bg-gray-850 p-3 text-xs text-gray-500 dark:text-gray-400">
					<div class="font-medium mb-1">{$i18n.t('Band Preview')}</div>
					<div class="space-y-1">
						<div>🟢 <strong>HIGH</strong>: ≥{confidenceHighThreshold}% + full retrieval</div>
						<div>🟠 <strong>MODERATE</strong>: {confidenceMediumThreshold}%–{confidenceHighThreshold - 1}% or partial retrieval</div>
						<div>🔴 <strong>LOW</strong>: &lt;{confidenceMediumThreshold}% or ≤1 section</div>
					</div>
				</div>
			{/if}
		</div>
	</div>

	<div class="flex justify-end pt-3">
		<button
			class="px-3.5 py-1.5 text-sm font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-full"
			type="submit"
		>
			{$i18n.t('Save')}
		</button>
	</div>
</form>
