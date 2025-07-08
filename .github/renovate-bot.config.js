module.exports = {
  allowedEnv: ['RENOVATE_*', 'NPM_TOKEN', 'COREPACK_*'],
  autodiscoverTopics: ["renovate-enabled"],
  onboarding: false,
  requireConfig: "optional",
  platform: "github",
  autodiscover: false,
  repositories: [
     "ashmere/RenovateAgent"
  ],
  configMigration: true,
  platformCommit: "enabled",
  timezone: "Europe/London",
  forkProcessing: "enabled", // Forks are enabled
  // Allow passing of all environment variables to package managers
  exposeAllEnv: true,
  // Allow Renovate to update the lockfile with scripts and plugins
  allowPlugins: true,
  allowScripts: true,
  ignoreScripts: false,
};
