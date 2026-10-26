// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

const repo = 'https://github.com/ntanwir10/codesage-algolia-challenge';

// https://astro.build/config
export default defineConfig({
	site: 'https://codesage-docs.vercel.app',
	integrations: [
		starlight({
			title: 'CodeSage',
			description:
				'Index codebases into Algolia and search them from Claude Desktop over MCP, or from a live web dashboard.',
			logo: { src: './src/assets/logo.svg' },
			favicon: '/favicon.svg',
			components: { Hero: './src/components/Hero.astro' },
			social: [{ icon: 'github', label: 'GitHub', href: repo }],
			editLink: { baseUrl: `${repo}/edit/master/site/` },
			customCss: [
				'@fontsource/ibm-plex-sans/400.css',
				'@fontsource/ibm-plex-sans/500.css',
				'@fontsource/ibm-plex-sans/600.css',
				'@fontsource/ibm-plex-sans/700.css',
				'@fontsource/ibm-plex-mono/400.css',
				'@fontsource/ibm-plex-mono/500.css',
				'./src/styles/custom.css',
			],
			sidebar: [
				{
					label: 'Start here',
					items: [
						{ label: 'Introduction', slug: 'docs/introduction' },
						{ label: 'Quick start', slug: 'docs/quick-start' },
						{ label: 'Installation in depth', slug: 'docs/installation' },
					],
				},
				{
					label: 'Guides',
					items: [
						{ label: 'Web dashboard', slug: 'docs/guides/web-dashboard' },
						{ label: 'Claude Desktop', slug: 'docs/guides/claude-desktop' },
						{ label: 'Other git hosts', slug: 'docs/guides/other-git-hosts' },
						{ label: 'Using the REST API', slug: 'docs/guides/rest-api' },
						{ label: 'Docker dev stack', slug: 'docs/guides/docker' },
						{ label: 'Production deployment', slug: 'docs/guides/production' },
					],
				},
				{
					label: 'How it works',
					items: [
						{ label: 'Architecture', slug: 'docs/concepts/architecture' },
						{ label: 'Indexing pipeline', slug: 'docs/concepts/indexing-pipeline' },
						{ label: 'Search and the Algolia index', slug: 'docs/concepts/search' },
						{ label: 'Data model', slug: 'docs/concepts/data-model' },
						{ label: 'Security model', slug: 'docs/concepts/security' },
					],
				},
				{
					label: 'Reference',
					items: [
						{ label: 'MCP tools', slug: 'docs/reference/mcp-tools' },
						{ label: 'MCP endpoints and errors', slug: 'docs/reference/mcp-endpoints' },
						{ label: 'REST API', slug: 'docs/reference/rest-api' },
						{ label: 'WebSocket protocol', slug: 'docs/reference/websocket' },
						{ label: 'Configuration', slug: 'docs/reference/configuration' },
						{ label: 'Commands', slug: 'docs/reference/commands' },
						{ label: 'Supported languages', slug: 'docs/reference/languages' },
					],
				},
				{
					label: 'Help',
					items: [
						{ label: 'Troubleshooting', slug: 'docs/troubleshooting' },
						{ label: 'Known limitations', slug: 'docs/limitations' },
						{ label: 'FAQ', slug: 'docs/faq' },
						{ label: 'Development', slug: 'docs/development' },
					],
				},
			],
		}),
	],
});
