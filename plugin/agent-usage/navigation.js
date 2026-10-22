// Route selection shared with the TUI and exercised without a terminal renderer.
export function latestRoot(context) {
 const time=s=>{const u=s.time?.updated;return typeof u==='number'?u:u instanceof Date?u.getTime():(u?.epochMillis??0);};
 return context.data.session.list().filter(s=>!s.parentID).sort((a,b)=>time(b)-time(a))[0]?.id;
}
export function createUsageNavigation(context) {
 return {
  initialRoot(data){return data?.rootID;},
  open(){
   const route=context.ui.router.current();
   if(route.type==='plugin'&&route.name==='agent-usage')return;
   const rootID=route.type==='session'?context.data.session.root(route.sessionID):latestRoot(context);
   context.ui.dialog.clear();
   context.ui.router.navigate({type:'plugin',name:'agent-usage',data:{rootID,previous:{...route}}});
  },
  close(){context.ui.router.navigate(context.ui.router.current().data?.previous??{type:'home'});},
 };
}
