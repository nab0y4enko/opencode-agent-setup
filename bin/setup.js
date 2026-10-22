#!/usr/bin/env node
import { main } from '../src/cli.js';
main().catch(error=>{console.error(error.name==='ExitPromptError'?'Cancelled; no pending wizard changes saved.':`Error: ${error.message}`);process.exitCode=1;});
